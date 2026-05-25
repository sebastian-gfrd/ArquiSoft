import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import jwt
import httpx
from fastapi import FastAPI, Depends, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

# Importaciones locales
from app.schemas import IntegrationRequest, JobAcceptedResponse
from app.adapters import AWSAdapter, GCPAdapter
from app.queue_manager import push_ingestion_job
from app.health import router as health_router

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("integration_api")

# Configuración leída de variables de entorno
DEV_MODE = os.getenv("DEV_MODE", "True").lower() in ("true", "1", "yes")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

app = FastAPI(
    title="BITE.co - Microservicio de Integración de Nube (FastAPI)",
    description=(
        "Microservicio 3: Motor de Ingesta Extensible. "
        "Recibe solicitudes, valida credenciales y delega a SQS de forma asíncrona."
    ),
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="https?://.*",  # Compatible con allow_credentials=True en Starlette
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar el router público de diagnóstico de salud (/health/)
app.include_router(health_router)

# Caché local en memoria de llaves públicas de AWS ALB (Cumplimiento de ASR-02 para evitar descargas repetitivas)
alb_public_keys_cache: Dict[str, str] = {}

async def get_alb_public_key(kid: str) -> str:
    """
    Descarga asíncronamente la llave pública regional de AWS ELB/ALB usando el Key ID (kid).
    Usa una caché local en memoria para mantener tiempos de respuesta < 100ms (ASR-02).
    """
    if kid in alb_public_keys_cache:
        return alb_public_keys_cache[kid]
    
    url = f"https://public-keys.auth.elb.{AWS_REGION}.amazonaws.com/{kid}"
    logger.info(f"[Security] Descargando llave pública de AWS ALB desde {url}")
    
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
    la cabecera x-amzn-oidc-data inyectada por el balanceador (Application Load Balancer - ALB).
    
    En DEV_MODE=True permite simular un inquilino si la cabecera no está presente,
    facilitando pruebas locales rápidas sin conexión física a AWS.
    """
    if DEV_MODE:
        if not x_amzn_oidc_data:
            logger.warning("[Security DEV_MODE] Cabecera ausente. Inyectando tenant simulado ID: 123")
            return {"tenant_id": 123, "user": "dev_user@bite.co"}
        
        try:
            # Decodificar el token JWT simulado sin verificación criptográfica
            payload = jwt.decode(x_amzn_oidc_data, options={"verify_signature": False})
            tenant_id = payload.get("https://bite.co/tenant_id", 123)
            try:
                tenant_id = int(tenant_id)
            except ValueError:
                tenant_id = 123
            return {"tenant_id": tenant_id, "user": payload.get("email", "simulated_user@bite.co")}
        except Exception as e:
            logger.error(f"[Security DEV_MODE] Error decodificando token simulado: {e}")
            return {"tenant_id": 123, "user": "dev_user@bite.co"}

    # --- FLUJO DE CONTROL DE SEGURIDAD ESTRICTA EN PRODUCCIÓN ---
    if not x_amzn_oidc_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Petición no autenticada. Falta cabecera de identidad del balanceador (x-amzn-oidc-data)"
        )
        
    try:
        # 1. Obtener cabecera del token para extraer el Key ID (kid)
        headers = jwt.get_unverified_header(x_amzn_oidc_data)
        kid = headers.get("kid")
        alg = headers.get("alg", "ES256")
        
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de ALB inválido: Falta identificador de llave 'kid'"
            )
            
        # 2. Descargar llave pública de la región de AWS ALB
        public_key = await get_alb_public_key(kid)
        
        # 3. Decodificar y verificar criptográficamente la firma usando la llave pública regional
        payload = jwt.decode(x_amzn_oidc_data, public_key, algorithms=[alg])
        
        # 4. Extraer el tenant_id y castearlo a entero
        tenant_id_raw = payload.get("https://bite.co/tenant_id")
        if not tenant_id_raw:
            tenant_id_raw = payload.get("sub", "0")
            
        try:
            tenant_id = int(tenant_id_raw)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El tenant_id extraído del token de identidad no es un entero válido"
            )
            
        return {
            "tenant_id": tenant_id,
            "user": payload.get("email"),
            "claims": payload
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token de identidad inyectado por el balanceador ha expirado"
        )
    except jwt.InvalidTokenError as e:
        logger.error(f"[Security Violation] Spoofing o JWT de ALB inválido detectado: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firma de identidad de ALB inválida o manipulada"
        )

# Endpoint Multitenant Protegido
@app.post(
    "/api/v1/integration/ingest",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED
)
async def ingest_cloud_data(
    request: IntegrationRequest,
    current_user: Dict[str, Any] = Depends(get_current_tenant)
):
    """
    Endpoint principal para recibir solicitudes de integración de nube (AWS / GCP).
    
    Flujo de ejecución:
    1. Verifica que el inquilino autenticado en el JWT coincida con el tenant_id solicitado (Multi-tenancy Isolation).
    2. Instancia dinámicamente el adaptador correcto (AWSAdapter / GCPAdapter) aplicando el Patrón Adapter.
    3. Ejecuta la validación sintáctica de credenciales localmente (sin llamadas de red bloqueantes).
    4. Si es válida, delega asíncronamente el trabajo a la cola SQS de Amazon AWS.
    5. Retorna inmediatamente HTTP 202 Accepted, liberando al cliente en milisegundos (ASR-03).
    """
    # 1. Aislamiento Multi-inquilino
    if current_user["tenant_id"] != request.tenant_id:
        logger.warning(
            f"[Security Intrusión] Usuario {current_user['user']} (tenant {current_user['tenant_id']}) "
            f"intentó realizar ingesta de nube para el tenant '{request.tenant_id}'"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: El token no pertenece al tenant solicitado"
        )

    # 2. Instanciación Dinámica (Patrón Adapter)
    provider_upper = request.provider.upper()
    if provider_upper == "AWS":
        adapter = AWSAdapter(request.credentials)
    elif provider_upper == "GCP":
        adapter = GCPAdapter(request.credentials)
    else:
        # Teóricamente mitigado por Pydantic, pero se añade como defensa en profundidad
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Proveedor no soportado: {request.provider}"
        )

    # 3. Validación Sintáctica (Rápida y No Bloqueante para ASR-02)
    if not adapter.validate_credentials():
        logger.error(
            f"[Validation Failure] Credenciales con formato inválido para {provider_upper} "
            f"(Tenant: {request.tenant_id}, Proyecto: {request.project_id})"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Estructura o formato de credenciales inválido para el proveedor {provider_upper}."
        )

    # 4. Construir payload normalizado e independiente de la nube
    payload = adapter.build_ingestion_payload()

    # 5. Encolamiento asíncrono e inmutable en SQS
    try:
        task_id = await push_ingestion_job(
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            provider=provider_upper,
            payload=payload
        )
    except Exception as e:
        logger.error(f"[Queue Service Failure] No se pudo escribir en SQS: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del sistema al registrar el trabajo de ingesta asíncrona."
        )

    # 6. Respuesta inmediata HTTP 202
    return JobAcceptedResponse(
        task_id=task_id,
        status="queued",
        timestamp=datetime.now(timezone.utc)
    )

# Envoltura para AWS Lambda
handler = Mangum(app)

