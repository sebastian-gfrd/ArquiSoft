import json
import logging
import boto3
from botocore.config import Config
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Tenant, Project

logger = logging.getLogger(__name__)

# Configuración del cliente boto3 con timeouts ultra-bajos para resguardar la latencia (ASR-02)
# connect_timeout = 0.2s, read_timeout = 0.5s y max_attempts = 0 (evita reintentos bloqueantes síncronos)
aws_config = Config(
    connect_timeout=0.2,
    read_timeout=0.5,
    retries={'max_attempts': 0}
)


def get_eventbridge_client():
    """
    Retorna una instancia del cliente de boto3 configurada para interactuar con Amazon EventBridge.
    Soporta credenciales estáticas y roles IAM de AWS (ECS Fargate Task Role).
    """
    kwargs = {
        'region_name': getattr(settings, 'AWS_REGION_NAME', 'us-east-1'),
        'config': aws_config
    }
    if getattr(settings, 'AWS_ACCESS_KEY_ID', None):
        kwargs['aws_access_key_id'] = settings.AWS_ACCESS_KEY_ID
    if getattr(settings, 'AWS_SECRET_ACCESS_KEY', None):
        kwargs['aws_secret_access_key'] = settings.AWS_SECRET_ACCESS_KEY
        
    return boto3.client('events', **kwargs)


@receiver(post_save, sender=Tenant)
def publicar_evento_tenant(sender, instance, created, **kwargs):
    """
    Publica un evento a Amazon EventBridge cada vez que un Tenant es creado o actualizado.
    Garantiza consistencia eventual asíncrona sin comprometer la base de datos local.
    """
    detail_type = "TenantCreated" if created else "TenantUpdated"
    event_bus_name = getattr(settings, 'EVENTBRIDGE_BUS_NAME', 'bite-event-bus')
    
    event_detail = {
        "id": instance.id,
        "nombre": instance.nombre,
        "estado": instance.estado,
        "plan": instance.plan
    }
    
    entry = {
        "Source": "bite.core",
        "DetailType": detail_type,
        "Detail": json.dumps(event_detail),
        "EventBusName": event_bus_name
    }
    
    logger.info(f"Preparando envío de evento EventBridge {detail_type} para Tenant ID {instance.id}")
    
    try:
        client = get_eventbridge_client()
        response = client.put_events(Entries=[entry])
        
        # Analizar respuesta de EventBridge
        failed_entry_count = response.get('FailedEntryCount', 0)
        if failed_entry_count > 0:
            logger.error(
                f"Error al enviar evento {detail_type} a EventBridge para Tenant ID {instance.id}. "
                f"Detalle de la respuesta: {response.get('Entries')}"
            )
        else:
            logger.info(f"Evento {detail_type} enviado exitosamente a EventBridge para Tenant ID {instance.id}")
            
    except Exception as e:
        # Bloque try/except robusto para resiliencia (ASR-04/05). La falla no debe abortar la transacción local.
        logger.error(
            f"Falla de red o conexión al publicar evento {detail_type} a Amazon EventBridge para Tenant ID {instance.id}. "
            f"Error: {str(e)}",
            exc_info=True
        )


@receiver(post_save, sender=Project)
def publicar_evento_proyecto(sender, instance, created, **kwargs):
    """
    Publica un evento a Amazon EventBridge cada vez que un Proyecto es creado o actualizado.
    Garantiza consistencia eventual asíncrona sin comprometer la base de datos local.
    """
    detail_type = "ProjectCreated" if created else "ProjectUpdated"
    event_bus_name = getattr(settings, 'EVENTBRIDGE_BUS_NAME', 'bite-event-bus')
    
    event_detail = {
        "id": instance.id,
        "nombre": instance.nombre,
        "tenant_id": instance.tenant.id
    }
    
    entry = {
        "Source": "bite.core",
        "DetailType": detail_type,
        "Detail": json.dumps(event_detail),
        "EventBusName": event_bus_name
    }
    
    logger.info(f"Preparando envío de evento EventBridge {detail_type} para Proyecto ID {instance.id}")
    
    try:
        client = get_eventbridge_client()
        response = client.put_events(Entries=[entry])
        
        # Analizar respuesta de EventBridge
        failed_entry_count = response.get('FailedEntryCount', 0)
        if failed_entry_count > 0:
            logger.error(
                f"Error al enviar evento {detail_type} a EventBridge para Proyecto ID {instance.id}. "
                f"Detalle de la respuesta: {response.get('Entries')}"
            )
        else:
            logger.info(f"Evento {detail_type} enviado exitosamente a EventBridge para Proyecto ID {instance.id}")
            
    except Exception as e:
        # Bloque try/except robusto para resiliencia (ASR-04/05). La falla no debe abortar la transacción local.
        logger.error(
            f"Falla de red o conexión al publicar evento {detail_type} a Amazon EventBridge para Proyecto ID {instance.id}. "
            f"Error: {str(e)}",
            exc_info=True
        )
