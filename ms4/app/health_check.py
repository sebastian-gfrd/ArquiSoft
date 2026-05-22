import os
import sys
import logging
import asyncio
from sqlalchemy import text

# Importaciones locales
# Asegurar que el directorio ms4/ esté en el path para importaciones correctas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.celery_app import app as celery_app
from app.database import AsyncSessionLocal

# Configurar logging para salida legible en el recolector de logs de AWS CloudWatch
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [HEALTH_PROBE] %(message)s"
)
logger = logging.getLogger("health_check")

async def check_database_connection() -> bool:
    """
    Verifica que la conexión al nodo Writer de Analytics DB pasando por RDS Proxy
    se encuentre activa y respondiendo a consultas.
    """
    logger.info("Verificando conectividad con Analytics DB...")
    try:
        async with AsyncSessionLocal() as session:
            # Ejecución de consulta trivial de ping a la base de datos
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
            if value == 1:
                logger.info("Conexión a Analytics DB: EXITOSA (SELECT 1 -> OK)")
                return True
            else:
                logger.error(f"Conexión a Analytics DB: FALLIDA (Retornó valor inesperado: {value})")
                return False
    except Exception as e:
        logger.error(f"Conexión a Analytics DB: FALLIDA - Error: {e}", exc_info=True)
        return False

def check_celery_broker_and_workers() -> bool:
    """
    Verifica que el broker de Celery esté respondiendo y que el proceso worker esté activo.
    Usa control.ping() para verificar la vitalidad operativa del motor de tareas.
    """
    logger.info("Verificando vitalidad de Celery Worker & Broker...")
    try:
        # Enviamos un ping a todos los workers activos conectados al broker
        # timeout=3.0 evita esperas indefinidas si el broker está caído
        ping_responses = celery_app.control.ping(timeout=3.0)
        
        # En AWS SQS o entornos con colas, control.ping() nos dice si hay hilos respondiendo.
        # En desarrollo local sin workers corriendo en segundo plano, esto podría estar vacío.
        # Si estamos en modo de desarrollo local (DEV_MODE) y no hay workers iniciados todavía,
        # verificamos al menos que podamos conectarse al Broker de Kombu de forma exitosa.
        if not ping_responses:
            dev_mode = os.getenv("DEV_MODE", "True").lower() in ("true", "1", "yes")
            if dev_mode:
                logger.warning("No se detectaron Celery Workers activos vía ping. Verificando solo conexión al Broker local...")
                with celery_app.connection() as conn:
                    conn.connect()
                logger.info("Conexión al Broker de Celery (DEV_MODE): EXITOSA")
                return True
            else:
                logger.error("No se recibieron respuestas 'pong' de ningún Celery Worker activo.")
                return False
        
        logger.info(f"Ping exitoso. Workers respondiendo: {ping_responses}")
        return True
    except Exception as e:
        logger.error(f"Vitalidad de Celery: FALLIDA - Error: {e}", exc_info=True)
        return False

async def main():
    logger.info("=== INICIANDO EXAMEN DE SALUD (HEALTH CHECK PROBE) ===")
    
    # 1. Comprobar salud de la Base de Datos
    db_ok = await check_database_connection()
    
    # 2. Comprobar salud del Broker / Workers
    celery_ok = check_celery_broker_and_workers()
    
    if db_ok and celery_ok:
        logger.info("=== RESULTADO: CONTENEDOR SALUDABLE (HEALTHY) ===")
        sys.exit(0)
    else:
        logger.error("=== RESULTADO: CONTENEDOR INESTABLE (UNHEALTHY) ===")
        sys.exit(1)

if __name__ == "__main__":
    # Corremos el event loop asíncrono
    asyncio.run(main())
