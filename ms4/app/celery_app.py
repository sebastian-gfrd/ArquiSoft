import os
import json
import logging
from celery import Celery, bootsteps
from kombu import Consumer, Queue

# Configuración de logging para visibilidad operativa de ECS Fargate
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("celery_worker")

# Cargar configuración desde variables de entorno
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
DEV_MODE = os.getenv("DEV_MODE", "True").lower() in ("true", "1", "yes")

# Instancia central de Celery
app = Celery("bite_worker")

# Determinar broker según el entorno
if SQS_QUEUE_URL:
    logger.info(f"[Celery CONFIG] SQS detectado como broker en URL: {SQS_QUEUE_URL}")
    broker_url = "sqs://"
    broker_transport_options = {
        "region": AWS_REGION,
        "predefined_queues": {
            "bite_worker": {
                "url": SQS_QUEUE_URL
            }
        },
        "wait_time_seconds": 10  # Long polling de 10 segundos para optimizar y reducir costos de API SQS
    }
else:
    logger.warning("[Celery CONFIG] SQS_QUEUE_URL no definida. Usando fallback de desarrollo (memory://)...")
    broker_url = os.getenv("CELERY_BROKER_URL", "memory://")
    broker_transport_options = {}

app.conf.update(
    broker_url=broker_url,
    broker_transport_options=broker_transport_options,
    task_default_queue="bite_worker",
    
    # ASR-03 Ajuste de Rendimiento Crítico:
    # Prefetch Multiplier en 1 para que el Worker no acapare múltiples tareas/archivos pesados de 2GB de forma simultánea.
    # Esto garantiza distribución balanceada en el clúster Fargate.
    worker_prefetch_multiplier=1,
    
    # Configuración de deserialización para máxima flexibilidad operativa
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Confirmar las tareas en la cola únicamente cuando terminen con éxito (Acks Late)
    # Si el contenedor se cae procesando, el archivo de 2GB se reintenta por otro worker saludable.
    task_acks_late=True,
    worker_cancel_long_time_to_run_tasks=True,
)

# Custom Consumer Bootstep para interceptar los mensajes JSON planos enviados por MS3
# y encolarlos asíncronamente como tareas estructuradas de Celery.
class RawSQSConsumer(bootsteps.ConsumerStep):
    """
    Bootstep de Kombu que escucha en la cola de SQS para procesar los mensajes planos
    que provienen directamente de Microservicio 3 (FastAPI) sin metadatos nativos de Celery.
    """
    def get_consumers(self, channel, default_consumers):
        queue = Queue("bite_worker")
        
        def handle_message(body, message):
            try:
                # Decodificación resiliente del cuerpo del mensaje
                if isinstance(body, str):
                    data = json.loads(body)
                else:
                    data = body
                
                logger.info(f"[SQS Consumer] Recibido mensaje crudo: {data}")
                
                # Extraer propiedades del payload inmutable de integración
                tenant_id = data.get("tenant_id")
                project_id = data.get("project_id")
                provider = data.get("provider")
                payload = data.get("payload")
                
                # Verificar campos obligatorios para la ingesta
                if all(v is not None for v in [tenant_id, project_id, provider]):
                    # Despachamos asíncronamente a la tarea registrada de Celery
                    from app.tasks import process_cloud_billing
                    process_cloud_billing.delay(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        provider=provider,
                        cloud_credentials=payload
                    )
                    logger.info(f"[SQS Consumer] Mensaje despachado a la tarea Celery. Tenant: {tenant_id}, Project: {project_id}")
                else:
                    # Si el mensaje contiene "task", probablemente es un mensaje de Celery nativo, no lo consumimos aquí
                    if "task" in data:
                        logger.info("[SQS Consumer] Mensaje con formato nativo de Celery. Ignorando en este paso.")
                        return
                    
                    logger.warning(f"[SQS Consumer] Mensaje inválido omitido (falta tenant_id, project_id o provider): {data}")
            except Exception as e:
                logger.error(f"[SQS Consumer] Error al deserializar e inyectar el mensaje: {e}", exc_info=True)
            finally:
                # Ack obligatorio para limpiar el mensaje de SQS y evitar bucles infinitos de visibilidad
                message.ack()

        return [
            Consumer(
                channel,
                queues=[queue],
                callbacks=[handle_message],
                accept=["json", "text/plain"]
            )
        ]

# Registrar el bootstep personalizado si estamos conectados a la cola de SQS real
if SQS_QUEUE_URL:
    app.steps['consumer'].add(RawSQSConsumer)
    logger.info("[Celery CONFIG] Bootstep de SQS Raw Consumer registrado exitosamente.")
