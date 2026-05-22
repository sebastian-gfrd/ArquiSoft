import time
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from app.database import get_db_session
from app.cache import redis_client

logger = logging.getLogger("analytics_health")
router = APIRouter()

async def check_database(db: AsyncSession) -> tuple[str, float | None]:
    """
    Verifica la conexión a la base de datos de analítica ejecutando 'SELECT 1'.
    Retorna una tupla (estado, latencia_en_ms).
    """
    start_time = time.perf_counter()
    try:
        # Ejecutar SELECT 1 de forma completamente asíncrona
        await db.execute(text("SELECT 1"))
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        return "healthy", latency
    except Exception as e:
        logger.error(f"[Health Check DB] Fallo en la base de datos: {e}")
        return f"unhealthy (error: {str(e)})", None

async def check_redis() -> tuple[str, float | None]:
    """
    Verifica la conexión a Redis enviando un comando PING.
    Retorna una tupla (estado, latencia_en_ms).
    """
    start_time = time.perf_counter()
    try:
        # Ejecutar PING de forma asíncrona a Redis
        await redis_client.ping()
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        return "healthy", latency
    except Exception as e:
        logger.error(f"[Health Check Redis] Fallo en el cliente Redis: {e}")
        return f"unhealthy (error: {str(e)})", None

@router.get("/health/", status_code=status.HTTP_200_OK)
async def health_check(db: AsyncSession = Depends(get_db_session)):
    """
    Endpoint público de diagnóstico de salud.
    
    Verifica de manera concurrente (usando asyncio.gather) la salud y latencia
    de la réplica de Aurora PostgreSQL y de Amazon ElastiCache (Redis).
    
    Si algún servicio no responde, retorna un código HTTP 503 (Service Unavailable)
    para indicarle al Application Load Balancer (ALB) que retire este nodo.
    """
    # Ejecución concurrente asíncrona para maximizar rendimiento
    db_task = check_database(db)
    redis_task = check_redis()
    
    db_result, redis_result = await asyncio.gather(db_task, redis_task)
    
    db_status, db_latency = db_result
    redis_status, redis_latency = redis_result
    
    # Determinar estado general
    overall_status = "healthy"
    if db_status != "healthy" or redis_status != "healthy":
        overall_status = "degraded"
        
    response_data = {
        "status": overall_status,
        "services": {
            "database": {
                "status": db_status,
                "latency_ms": db_latency
            },
            "cache": {
                "status": redis_status,
                "latency_ms": redis_latency
            }
        }
    }
    
    if overall_status == "degraded":
        # Retorna 503 en caso de fallos graves
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response_data
        )
        
    return response_data
