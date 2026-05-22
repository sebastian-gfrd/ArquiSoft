import os
import time
import asyncio
import logging
import boto3
from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger("integration_health")
router = APIRouter()

# Configuración leída desde variables de entorno
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
DEV_MODE = os.getenv("DEV_MODE", "True").lower() in ("true", "1", "yes")

async def check_sqs_connectivity() -> tuple[str, float | None]:
    """
    Verifica la conexión y permisos de red hacia Amazon SQS.
    Mide el tiempo de respuesta de la cola.
    
    Para evitar bloquear el event loop, la llamada síncrona a boto3
    se ejecuta en un hilo secundario mediante 'asyncio.to_thread'.
    """
    start_time = time.perf_counter()
    
    # Simulación local si estamos en DEV_MODE y no se especificó cola real
    if DEV_MODE and not SQS_QUEUE_URL:
        await asyncio.sleep(0.015)  # Simular latencia de red típica
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        return "healthy (simulated)", latency
        
    if not SQS_QUEUE_URL:
        return "unhealthy (SQS_QUEUE_URL is not set)", None

    def _ping_sqs():
        """Llama a la API de SQS para leer atributos básicos de la cola."""
        # Se conecta de forma pasiva a SQS y solicita el QueueArn
        sqs_client = boto3.client("sqs", region_name=AWS_REGION)
        sqs_client.get_queue_attributes(
            QueueUrl=SQS_QUEUE_URL,
            AttributeNames=["QueueArn"]
        )

    try:
        # Ejecución concurrente no bloqueante
        await asyncio.to_thread(_ping_sqs)
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        return "healthy", latency
    except Exception as e:
        logger.error(f"[Health Check SQS] Fallo de conectividad a SQS ({SQS_QUEUE_URL}): {e}")
        return f"unhealthy (error: {str(e)})", None

@router.get("/health/", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Endpoint público de diagnóstico de salud para el balanceador de carga (ALB).
    
    Verifica de manera asíncrona la conectividad y latencia hacia la cola
    de Amazon SQS. Si la cola está caída o inaccesible (ej. fallo de credenciales IAM),
    responde con un HTTP 503 (Service Unavailable) para indicar degradación del servicio.
    """
    sqs_status, sqs_latency = await check_sqs_connectivity()
    
    # Determinar si el microservicio se considera saludable
    overall_status = "healthy"
    if "unhealthy" in sqs_status:
        overall_status = "degraded"
        
    response_data = {
        "status": overall_status,
        "services": {
            "sqs_queue": {
                "status": sqs_status,
                "latency_ms": sqs_latency
            }
        }
    }
    
    if overall_status == "degraded":
        logger.error(f"[Health Check Failed] Servicio degradado: {response_data}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response_data
        )
        
    return response_data
