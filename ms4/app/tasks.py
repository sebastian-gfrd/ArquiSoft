import os
import time
import random
import logging
import asyncio
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError
from celery import shared_task

# Importaciones locales
from app.celery_app import app
from app.database import AsyncSessionLocal
from app.models import ProcessedCost
from sqlalchemy import insert

logger = logging.getLogger("celery_tasks")

# Configuración leída de variables de entorno
DEV_MODE = os.getenv("DEV_MODE", "True").lower() in ("true", "1", "yes")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
ALERT_TIME_THRESHOLD_SECS = float(os.getenv("ALERT_TIME_THRESHOLD_SECS", "1.5"))
SENDER_EMAIL = os.getenv("SES_SENDER_EMAIL", "ops@bite.co")
RECIPIENT_EMAIL = os.getenv("SES_RECIPIENT_EMAIL", "admin@bite.co")

class CloudHandshakeError(Exception):
    """Excepción estructurada para errores de validación con el proveedor de nube."""
    def __init__(self, message: str, provider: str, details: dict):
        super().__init__(message)
        self.provider = provider
        self.details = details
        self.timestamp = datetime.utcnow()

async def _bulk_insert_costs(records: list):
    """
    Realiza la persistencia masiva de los registros analíticos consolidados.
    
    Abre una sesión asíncrona contra la base de datos de analítica (vía RDS Proxy)
    y ejecuta un bulk insert nativo para garantizar alta velocidad.
    """
    logger.info(f"[DB Persist] Iniciando inserción masiva de {len(records)} registros consolidados...")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Inserción masiva de alto rendimiento de SQLAlchemy 2.0
            await session.execute(insert(ProcessedCost), records)
    logger.info("[DB Persist] Inserción masiva completada exitosamente.")

def _send_ses_time_alert(tenant_id: int, project_id: int, duration: float):
    """
    Dispara una alerta simulada/real de correo vía Amazon SES noticiando
    que el tiempo de cómputo superó el umbral seguro.
    """
    subject = f"⚠️ [ALERTA FinOps] Exceso de Tiempo en Procesamiento Analítico - Tenant {tenant_id}"
    
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background-color: #f4f6f8; color: #333; }}
            .container {{ max-width: 600px; margin: 30px auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border-top: 4px solid #f44336; }}
            h2 {{ color: #d32f2f; margin-top: 0; }}
            .meta-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            .meta-table td {{ padding: 10px; border-bottom: 1px solid #eee; }}
            .meta-table td.label {{ font-weight: bold; width: 35%; color: #666; }}
            .meta-table td.value {{ color: #222; }}
            .warning-box {{ background-color: #ffebee; border-left: 4px solid #f44336; padding: 15px; border-radius: 4px; color: #c62828; margin: 20px 0; }}
            .footer {{ font-size: 12px; color: #999; text-align: center; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Alerta de Rendimiento de Procesador Analítico</h2>
            <div class="warning-box">
                <strong>Atención:</strong> La tarea de procesamiento de facturación pesada ha excedido el umbral seguro de ejecución de <strong>{ALERT_TIME_THRESHOLD_SECS} segundos</strong>.
            </div>
            <table class="meta-table">
                <tr>
                    <td class="label">Inquilino (Tenant ID)</td>
                    <td class="value">{tenant_id}</td>
                </tr>
                <tr>
                    <td class="label">Proyecto ID</td>
                    <td class="value">{project_id}</td>
                </tr>
                <tr>
                    <td class="label">Tiempo Registrado</td>
                    <td class="value"><strong>{duration:.3f} segundos</strong></td>
                </tr>
                <tr>
                    <td class="label">Umbral Configurado</td>
                    <td class="value">{ALERT_TIME_THRESHOLD_SECS} segundos</td>
                </tr>
                <tr>
                    <td class="label">Región AWS</td>
                    <td class="value">{AWS_REGION}</td>
                </tr>
            </table>
            <p>Se recomienda revisar la capacidad de procesamiento de las instancias AWS ECS Fargate, el dimensionamiento de Amazon RDS Proxy o la estructura del archivo CUR de entrada.</p>
            <div class="footer">
                Este correo fue generado automáticamente por el Microservicio 4 (Celery Worker) utilizando Amazon SES.
            </div>
        </div>
    </body>
    </html>
    """

    if DEV_MODE:
        # En modo de desarrollo local simulamos el envío para no requerir credenciales físicas configuradas
        logger.warning(
            f"\n"
            f"========================================================================\n"
            f" 📧 [SIMULACIÓN AMAZON SES] - ALERTA ENVIADA CON ÉXITO\n"
            f" De: {SENDER_EMAIL}\n"
            f" Para: {RECIPIENT_EMAIL}\n"
            f" Asunto: {subject}\n"
            f"------------------------------------------------------------------------\n"
            f" El proceso analítico del Tenant {tenant_id} tardó {duration:.3f}s (Umbral: {ALERT_TIME_THRESHOLD_SECS}s).\n"
            f" Correo enviado exitosamente vía sandbox de Amazon SES (Simulado).\n"
            f"========================================================================\n"
        )
        return

    # Envío real usando la API de boto3 SES
    try:
        ses_client = boto3.client("ses", region_name=AWS_REGION)
        response = ses_client.send_email(
            Source=SENDER_EMAIL,
            Destination={"ToAddresses": [RECIPIENT_EMAIL]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": html_body, "Charset": "UTF-8"}
                }
            }
        )
        logger.info(f"[SES Alert] Alerta de tiempo enviada con éxito. MessageId: {response['MessageId']}")
    except ClientError as e:
        logger.error(f"[SES Error] Error enviando alerta vía Amazon SES: {e.response['Error']['Message']}")

@shared_task(name="tasks.process_cloud_billing", bind=True)
def process_cloud_billing(self, tenant_id: int, project_id: int, provider: str, cloud_credentials: dict):
    """
    Tarea Celery principal encargada del procesamiento analítico pesado de costos (ASR-03).
    
    Flujo:
    1. Ejecuta validación profunda (Handshake) con el proveedor simulando/verificando credenciales.
    2. Simula procesamiento pesado de un archivo masivo de 2GB mediante iteración por chunks.
    3. Persiste masivamente los resultados (30 días de registros) en la Analytics DB de forma asíncrona.
    4. Controla los tiempos y dispara alertas vía Amazon SES si se supera el umbral configurado.
    """
    logger.info(
        f"[Task Start] Iniciando procesamiento de costos. "
        f"Tenant: {tenant_id} | Proyecto: {project_id} | Proveedor: {provider}"
    )
    
    start_time = time.time()
    
    # Extraer detalles específicos
    details = cloud_credentials.get("details", {}) if cloud_credentials else {}
    
    # ----------------------------------------------------
    # 1. VALIDACIÓN PROFUNDA (HANDSHAKE)
    # ----------------------------------------------------
    if provider.upper() == "AWS":
        bucket_name = details.get("s3_bucket", "bite-cost-reports")
        role_arn = details.get("role_arn", "")
        
        logger.info(f"[Handshake AWS] Validando existencia del bucket S3 '{bucket_name}' con el Role ARN '{role_arn}'...")
        
        if DEV_MODE:
            # Simulación en desarrollo
            time.sleep(0.3)
            if bucket_name == "non-existent-bucket":
                raise CloudHandshakeError(
                    message=f"Handshake fallido: El bucket S3 '{bucket_name}' no existe.",
                    provider="AWS",
                    details={"role_arn": role_arn, "s3_bucket": bucket_name}
                )
            logger.info(f"[Handshake AWS Success] Bucket '{bucket_name}' validado con éxito.")
        else:
            # Conexión real con AWS S3 usando boto3 (para ECS Fargate en producción)
            try:
                # Opcional: asumimos el rol temporal de IAM antes del handshake si role_arn está configurado
                s3_client = boto3.client("s3", region_name=AWS_REGION)
                s3_client.head_bucket(Bucket=bucket_name)
                logger.info(f"[Handshake AWS Success] Validación real del bucket S3 exitosa.")
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                error_msg = f"El bucket S3 '{bucket_name}' no existe o no tiene permisos de lectura (Error {error_code})."
                logger.error(f"[Handshake AWS Failure] {error_msg}")
                raise CloudHandshakeError(
                    message=error_msg,
                    provider="AWS",
                    details={"role_arn": role_arn, "s3_bucket": bucket_name, "aws_error_code": error_code}
                )
            except Exception as ex:
                error_msg = f"Error general de red al conectar con S3: {str(ex)}"
                logger.error(f"[Handshake AWS Failure] {error_msg}")
                raise CloudHandshakeError(
                    message=error_msg,
                    provider="AWS",
                    details={"role_arn": role_arn, "s3_bucket": bucket_name}
                )
    
    elif provider.upper() == "GCP":
        gcp_project = details.get("gcp_project_id", "bite-gcp-project")
        logger.info(f"[Handshake GCP] Validando conexión al Dataset BigQuery en el proyecto '{gcp_project}'...")
        
        if DEV_MODE:
            time.sleep(0.3)
            logger.info(f"[Handshake GCP Success] Proyecto GCP '{gcp_project}' validado con éxito.")
        else:
            # Validación esquelética real para GCP
            logger.info(f"[Handshake GCP Success] Conexión simulada exitosa en entorno real.")
            
    else:
        raise ValueError(f"Proveedor no soportado: '{provider}'")
        
    # ----------------------------------------------------
    # 2. PROCESAMIENTO Y AGREGACIÓN MATEMÁTICA DE DATOS (2GB)
    # ----------------------------------------------------
    logger.info("[Task Compute] Iniciando agregación y parsing del archivo masivo de facturación de 2GB...")
    
    # Simulamos el procesamiento pesado de 2GB diviendo el archivo en 5 bloques secuenciales
    total_chunks = 5
    for chunk in range(1, total_chunks + 1):
        # Cada chunk toma un poco de tiempo de CPU para simular operaciones matemáticas intensivas
        time.sleep(0.2)
        logger.info(f"[Task Compute] Procesado bloque {chunk}/{total_chunks} (400MB de CUR parsed y agregado)")
        
    # ----------------------------------------------------
    # 3. CONSOLIDACIÓN DE REGISTROS PARA INSERCIÓN MASIVA
    # ----------------------------------------------------
    # Generamos un consolidado de los últimos 30 días para insertar en bloque
    records_to_insert = []
    base_date = datetime.now().date()
    
    # Semilla aleatoria reproducible para propósitos de simulación
    random.seed(tenant_id + project_id)
    
    for day in range(30):
        fecha = base_date - timedelta(days=day)
        
        # Simulación realista de costos basados en el ID del proyecto
        costo_computo = round(random.uniform(100.0, 2000.0), 2)
        costo_almacenamiento = round(random.uniform(20.0, 400.0), 2)
        costo_otros = round(random.uniform(5.0, 150.0), 2)
        recursos_infrautilizados = random.randint(0, 12)
        
        records_to_insert.append({
            "tenant_id": tenant_id,
            "project_id": project_id,
            "provider": provider.upper(),
            "fecha_consumo": fecha,
            "costo_computo": costo_computo,
            "costo_almacenamiento": costo_almacenamiento,
            "costo_otros": costo_otros,
            "recursos_infrautilizados_count": recursos_infrautilizados
        })
        
    # ----------------------------------------------------
    # 4. PERSISTENCIA MASIVA (BULK INSERT)
    # ----------------------------------------------------
    # Dado que SQLAlchemy es asíncrono en BITE.co, ejecutamos la escritura en el loop asíncrono
    try:
        asyncio.run(_bulk_insert_costs(records_to_insert))
    except Exception as db_err:
        logger.critical(f"[DB Critical Failure] Fallo catastrófico al insertar registros analíticos: {db_err}", exc_info=True)
        raise db_err
        
    # ----------------------------------------------------
    # 5. CONTROL DE TIEMPO Y DISPARO DE ALERTAS (SES)
    # ----------------------------------------------------
    end_time = time.time()
    duration = end_time - start_time
    
    logger.info(
        f"[Task Success] Procesamiento analítico completado exitosamente. "
        f"Duración total: {duration:.3f} segundos | Registros guardados: {len(records_to_insert)}"
    )
    
    # Si la duración del cómputo supera el umbral seguro, enviamos la alerta de correo de forma inmediata
    if duration > ALERT_TIME_THRESHOLD_SECS:
        logger.warning(
            f"[Rendimiento Crítico] ¡El proceso excedió el umbral seguro! "
            f"Duración: {duration:.3f}s | Umbral: {ALERT_TIME_THRESHOLD_SECS}s"
        )
        _send_ses_time_alert(tenant_id, project_id, duration)
        
    return {
        "status": "success",
        "tenant_id": tenant_id,
        "project_id": project_id,
        "processed_records_count": len(records_to_insert),
        "duration_seconds": duration,
        "exceeded_threshold": duration > ALERT_TIME_THRESHOLD_SECS
    }
