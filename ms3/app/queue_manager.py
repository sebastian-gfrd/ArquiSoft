import os
import json
import logging
import asyncio
import boto3
from typing import Dict, Any

logger = logging.getLogger("queue_manager")

# Configuración de infraestructura mediante variables de entorno
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
DEV_MODE = os.getenv("DEV_MODE", "True").lower() in ("true", "1", "yes")

async def push_ingestion_job(tenant_id: int, project_id: int, provider: str, payload: dict) -> str:
    """
    Orquestador de mensajería asíncrona para Amazon SQS.
    
    Toma los datos de integración y los envía a la cola SQS de AWS.
    Para garantizar que la llamada de red bloqueante de boto3 no detenga el
    event loop de FastAPI, se delega su ejecución a un pool de hilos mediante
    'asyncio.to_thread'.
    
    El payload enviado al SQS contiene de forma inmutable y validada el 'tenant_id'
    y el 'project_id', logrando desacoplamiento y consistencia eventual sin
    consultar síncronamente al microservicio principal.
    """
    message_body = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "provider": provider,
        "payload": payload
    }
    
    # Modo desarrollo local: simula la inyección a SQS sin conexión física a AWS
    if DEV_MODE and not SQS_QUEUE_URL:
        import uuid
        simulated_msg_id = str(uuid.uuid4())
        logger.info(
            f"[SQS DEV MODE] Simulación de mensaje encolado con éxito. "
            f"MessageId: {simulated_msg_id} | Tenant: {tenant_id} | Project: {project_id}\n"
            f"Cuerpo del Mensaje: {json.dumps(message_body, indent=2)}"
        )
        # Pequeña latencia para simular el round-trip de red de forma realista
        await asyncio.sleep(0.05)
        return simulated_msg_id

    if not SQS_QUEUE_URL:
        raise ValueError(
            "Error de Configuración: La variable de entorno SQS_QUEUE_URL no está definida "
            "en entorno de producción."
        )

    def _send_to_sqs():
        """Llamada síncrona a la API de SQS usando boto3."""
        # Se asume que el contenedor o Lambda tiene credenciales IAM correctas (IAM Role para ECS/Lambda)
        sqs_client = boto3.client("sqs", region_name=AWS_REGION)
        
        response = sqs_client.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps(message_body)
        )
        return response.get("MessageId")

    try:
        # Ejecución no bloqueante en hilo secundario del event loop
        message_id = await asyncio.to_thread(_send_to_sqs)
        logger.info(
            f"[SQS Success] Mensaje enviado a la cola SQS. "
            f"SQS MessageId: {message_id} (Tenant: {tenant_id}, Project: {project_id})"
        )
        return message_id
    except Exception as e:
        logger.error(
            f"[SQS Error] Fallo al enviar mensaje a la cola SQS ({SQS_QUEUE_URL}): {e}"
        )
        raise e
