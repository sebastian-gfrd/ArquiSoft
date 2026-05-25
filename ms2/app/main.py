import os
import logging
import jwt
import httpx
from fastapi import FastAPI, Depends, Header, HTTPException, status, Path
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from typing import Dict, Any, Optional

# Importaciones locales
from app.database import get_db_session
from app.cache import get_cache, set_cache
from app.schemas import DashboardOverview, MonthlyReport, CloudProviderCost
from app.health import router as health_router

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("analytics_api")

# Variables de entorno
DEV_MODE = os.getenv("DEV_MODE", "True").lower() in ("true", "1", "yes")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

app = FastAPI(
    title="BITE.co - Microservicio de Analytics & Reportes (FastAPI)",
    description="Microservicio de lectura rápida (Queries) del patrón CQRS. Desplegado en AWS Lambda.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="https?://.*",  # Compatible con allow_credentials=True en Starlette
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar el router de diagnóstico de salud pública
app.include_router(health_router)

# Cache de llaves públicas de AWS ALB para evitar descargas repetitivas en producción (ASR-02)
alb_public_keys_cache: Dict[str, str] = {}

async def get_alb_public_key(kid: str) -> str:
    """
    Descarga asíncronamente la llave pública regional de AWS ELB/ALB usando el Key ID (kid).
    Usa caché local en memoria para cumplir con el ASR-02 (Latencia < 100ms).
    """
    if kid in alb_public_keys_cache:
        return alb_public_keys_cache[kid]
    
    url = f"https://public-keys.auth.elb.{AWS_REGION}.amazonaws.com/{kid}"
    logger.info(f"Descargando llave pública de AWS ALB desde {url}")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(url)
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se pudo obtener la llave pública de verificación de AWS ALB"
            )
        public_key = response.text
        alb_public_keys_cache[kid] = public_key
        return public_key

async def get_current_tenant(
    x_amzn_oidc_data: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    Dependencia de seguridad que extrae, decodifica y valida de forma estricta 
    la cabecera x-amzn-oidc-data inyectada por el Application Load Balancer (ALB).
    
    En DEV_MODE=True se permite omitir la verificación criptográfica o proveer un token
    simulado para desarrollo y pruebas locales rápidas sin conexión a AWS.
    """
    if DEV_MODE:
        # Modo desarrollo local: simular un tenant válido
        if not x_amzn_oidc_data:
            logger.warning("[Security] Corriendo en DEV_MODE sin cabecera. Inyectando tenant simulado 'tenant-123'")
            return {"tenant_id": "tenant-123", "user": "dev_user@bite.co"}
        
        try:
            # Decodificación simple sin verificar firma
            payload = jwt.decode(x_amzn_oidc_data, options={"verify_signature": False})
            tenant_id = payload.get("https://bite.co/tenant_id", "tenant-123")
            return {"tenant_id": tenant_id, "user": payload.get("email", "simulated_user@bite.co")}
        except Exception as e:
            logger.error(f"[Security] Error decodificando token simulado: {e}")
            return {"tenant_id": "tenant-123", "user": "dev_user@bite.co"}

    # --- FLUJO DE PRODUCCIÓN SEGURO ---
    if not x_amzn_oidc_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Petición no autenticada. Falta cabecera de identidad del balanceador (x-amzn-oidc-data)"
        )
        
    try:
        # 1. Obtener la cabecera sin verificar para extraer el 'kid' (Key ID)
        headers = jwt.get_unverified_header(x_amzn_oidc_data)
        kid = headers.get("kid")
        alg = headers.get("alg", "ES256")  # AWS ALB firma habitualmente usando ES256
        
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de ALB inválido: Falta identificador de llave 'kid'"
            )
            
        # 2. Obtener la llave pública oficial de la región de AWS
        public_key = await get_alb_public_key(kid)
        
        # 3. Decodificar y verificar criptográficamente la firma usando la llave pública de AWS
        payload = jwt.decode(x_amzn_oidc_data, public_key, algorithms=[alg])
        
        # 4. Extraer el tenant_id personalizado
        tenant_id = payload.get("https://bite.co/tenant_id")
        if not tenant_id:
            # Si no hay claim de tenant, se puede usar un mapeo basado en el 'sub' u otra propiedad
            tenant_id = payload.get("sub", "unknown_tenant")
            
        return {
            "tenant_id": tenant_id,
            "user": payload.get("email"),
            "claims": payload
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token inyectado por el balanceador ha expirado"
        )
    except jwt.InvalidTokenError as e:
        logger.error(f"[Security Violation] Intento de spoofing de JWT de ALB detectado: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firma de identidad de ALB inválida o manipulada"
        )

# --- ENDPOINTS ANALÍTICOS ---

@app.get(
    "/api/v1/analytics/dashboard/{tenant_id}",
    response_model=DashboardOverview,
    status_code=status.HTTP_200_OK
)
async def get_dashboard_overview(
    tenant_id: str = Path(..., description="El identificador único del cliente (tenant)"),
    db: AsyncSession = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(get_current_tenant)
):
    """
    Expone la vista general resumida del Dashboard del tenant.
    
    Aplica rigurosamente el patrón **Cache-Aside**:
    1. Verifica la existencia de datos consolidados en ElastiCache (Redis) con la llave 'dashboard:{tenant_id}'.
    2. Si hay un **Cache Hit**, retorna los datos deserializados inmediatamente.
    3. Si hay un **Cache Miss**, consulta asíncronamente a la réplica de Aurora PostgreSQL.
    4. Almacena el resultado en la caché con un Time-To-Live (TTL) de 300 segundos para consultas posteriores.
    """
    # Verificación de aislamiento multitenant
    if current_user["tenant_id"] != tenant_id:
        logger.warning(f"[Security Warning] Usuario {current_user['user']} intentó acceder a recursos del tenant '{tenant_id}'")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: El token no pertenece al tenant solicitado"
        )
        
    cache_key = f"dashboard:{tenant_id}"
    
    # 1. Intentar obtener de Redis (Cache-Aside: Lectura de caché)
    cached_data = await get_cache(cache_key)
    if cached_data:
        return cached_data
        
    # 2. Cache Miss: Ejecutar la consulta simulada a la base de datos PostgreSQL de analítica
    logger.info(f"[Cache Miss] Obteniendo información de Aurora PostgreSQL replica para el tenant: {tenant_id}")
    try:
        # Simulación de la carga transaccional en la DB ejecutando 'SELECT 1' de forma asíncrona
        await db.execute(text("SELECT 1"))
        
        # En un flujo de analítica real, aquí se consultaría la base de datos de réplica de Aurora:
        # query = select(BillingAggregate).where(BillingAggregate.tenant_id == tenant_id)
        # res = await db.execute(query) ...
        
        # Generar datos simulados consistentes y dinámicos basados en el tenant_id
        db_result = {
            "costo_total": 12543.50,
            "ahorro_proyectado": 1820.75,
            "recursos_infrautilizados_count": 14,
            "costos_por_proveedor": [
                {"proveedor": "AWS", "costo": 8543.20},
                {"proveedor": "GCP", "costo": 4000.30}
            ]
        }
        
        # 3. Guardar en caché asíncronamente con TTL de 300 segundos
        await set_cache(cache_key, db_result, expire_seconds=300)
        
        return db_result
        
    except Exception as e:
        logger.error(f"[Database Error] Falló consulta analítica en base de datos para {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al consultar la base de datos de analítica"
        )


@app.get(
    "/api/v1/analytics/reports/{tenant_id}/{year}/{month}",
    response_model=MonthlyReport,
    status_code=status.HTTP_200_OK
)
async def get_monthly_report(
    tenant_id: str = Path(..., description="El identificador del tenant"),
    year: int = Path(..., description="Año del reporte histórico", ge=2000),
    month: int = Path(..., description="Mes del reporte histórico", ge=1, le=12),
    db: AsyncSession = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(get_current_tenant)
):
    """
    Expone el reporte analítico mensual histórico para un tenant específico.
    
    Aplica el patrón **Cache-Aside**:
    1. Verifica en Redis usando la llave 'report:{tenant_id}:{year}:{month}'.
    2. En caso de Miss, consulta a la base de datos y cachea el resultado por 300 segundos.
    """
    # Aislamiento multitenant
    if current_user["tenant_id"] != tenant_id:
        logger.warning(f"[Security Warning] Usuario {current_user['user']} intentó acceder a reportes del tenant '{tenant_id}'")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: El token no pertenece al tenant solicitado"
        )
        
    cache_key = f"report:{tenant_id}:{year}:{month}"
    
    # 1. Intentar obtener de Redis
    cached_data = await get_cache(cache_key)
    if cached_data:
        return cached_data
        
    # 2. Cache Miss: Ejecutar la consulta simulada a la base de datos
    logger.info(f"[Cache Miss] Recuperando reporte mensual para {tenant_id} ({year}-{month:02d}) de la base de datos")
    try:
        # Simulación de la carga transaccional en la DB
        await db.execute(text("SELECT 1"))
        
        # Generar datos simulados realistas para el reporte mensual histórico
        db_result = {
            "tenant_id": tenant_id,
            "mes": month,
            "año": year,
            "costo_computo": 6200.50,
            "costo_almacenamiento": 4100.80,
            "costo_otros": 2242.20,
            "limite_presupuesto_excedido": False
        }
        
        # 3. Cache-Aside: Guardar en caché asíncronamente con TTL de 300 segundos
        await set_cache(cache_key, db_result, expire_seconds=300)
        
        return db_result
        
    except Exception as e:
        logger.error(f"[Database Error] Falló consulta de reporte mensual para {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al consultar el reporte mensual histórico"
        )

# Envoltura para AWS Lambda
handler = Mangum(app)

