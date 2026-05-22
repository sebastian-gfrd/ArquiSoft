import os
import sys
import asyncio
from datetime import datetime

# Agregar la ruta base del proyecto
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configurar variables de entorno antes de importar componentes
os.environ["DEV_MODE"] = "True"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test_analytics.db"
os.environ["ALERT_TIME_THRESHOLD_SECS"] = "0.5"  # Umbral bajo para disparar la alerta de tiempo en pruebas

from app.database import engine, Base, AsyncSessionLocal
from app.tasks import process_cloud_billing, CloudHandshakeError
from app.models import ProcessedCost
from sqlalchemy import select, func

async def _init_database():
    """Inicializa la base de datos local SQLite de prueba."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

async def _verify_database_records():
    """Consulta la base de datos SQLite para verificar que existan los 30 registros diarios."""
    async with AsyncSessionLocal() as session:
        # Obtener total de registros
        total_stmt = select(func.count(ProcessedCost.id))
        total_result = await session.execute(total_stmt)
        total_count = total_result.scalar()
        
        # Obtener muestras
        sample_stmt = select(ProcessedCost).limit(3)
        sample_result = await session.execute(sample_stmt)
        samples = sample_result.scalars().all()
        
        print(f"   Registros totales persistidos en la base: {total_count}")
        print("   Muestras de los registros guardados:")
        for r in samples:
            print(f"     - {r}")
            
        assert total_count == 30

async def _verify_health_db():
    """Verifica que el componente de health_check se conecte a la DB exitosamente."""
    from app.health_check import check_database_connection
    return await check_database_connection()

def run_test():
    print("======================================================================")
    print(" === INICIANDO VERIFICACION DE SANIDAD DEL CELERY WORKER (MS4) ===")
    print("======================================================================")
    
    # 1. Crear tablas en la base de datos de pruebas local SQLite
    print("\n[Paso 1] Creando tablas en base de datos local SQLite de pruebas...")
    asyncio.run(_init_database())
    print("Base de datos local inicializada.")
    
    # 2. Probar Validación Profunda (Handshake) con bucket inexistente
    print("\n[Paso 2] Verificando validacion profunda (Handshake con bucket invalido)...")
    bad_credentials = {
        "details": {
            "s3_bucket": "non-existent-bucket",
            "role_arn": "arn:aws:iam::123456789012:role/BiteIntegrationRole"
        }
    }
    
    try:
        # Invocación directa síncrona (como lo hace el thread pool de Celery)
        process_cloud_billing(
            tenant_id=999,
            project_id=888,
            provider="AWS",
            cloud_credentials=bad_credentials
        )
        print("ERROR: El handshake debio fallar por bucket inexistente.")
        sys.exit(1)
    except CloudHandshakeError as e:
        print(f"EXITO: Se capturo correctamente la excepcion de handshake: {e}")
        print(f"   Detalles del Handshake Fallido: {e.details}")
        
    # 3. Probar Flujo Completo Exitoso (Handshake, Procesamiento, Persistencia, Alerta)
    print("\n[Paso 3] Probando procesamiento de AWS CUR exitoso (2GB)...")
    good_credentials = {
        "details": {
            "s3_bucket": "bite-billing-bucket",
            "role_arn": "arn:aws:iam::123456789012:role/BiteIntegrationRole"
        }
    }
    
    # Esta ejecución ocurre fuera de cualquier loop de asyncio activo, simulando exactamente Fargate
    result = process_cloud_billing(
        tenant_id=123,
        project_id=456,
        provider="AWS",
        cloud_credentials=good_credentials
    )
    
    print("\nResultados de Ejecucion Retornados por la Tarea:")
    for k, v in result.items():
        print(f"   - {k}: {v}")
        
    assert result["status"] == "success"
    assert result["processed_records_count"] == 30
    assert result["exceeded_threshold"] is True, "El proceso debio superar el umbral de 0.5s"
    print("Tarea ejecutada correctamente y aserciones basicas de rendimiento aprobadas.")
    
    # 4. Verificar datos guardados en la base de datos
    print("\n[Paso 4] Consultando persistencia masiva en base de datos local...")
    asyncio.run(_verify_database_records())
    print("Persistencia masiva validada de forma exitosa.")
    
    # 5. Probar Probe de Salud
    print("\n[Paso 5] Validando script de monitoreo de salud (health_check.py)...")
    db_ok = asyncio.run(_verify_health_db())
    
    # Para el Celery check
    from app.health_check import check_celery_broker_and_workers
    celery_ok = check_celery_broker_and_workers()
    
    print(f"   Estado DB: {'SALUDABLE' if db_ok else 'CAIDA'}")
    print(f"   Estado Celery Broker: {'SALUDABLE' if celery_ok else 'CAIDO'}")
    
    assert db_ok is True
    assert celery_ok is True
    print("Script de monitoreo de salud operativo.")
    
    print("\n======================================================================")
    print(" === TODAS LAS PRUEBAS DE SANIDAD SE COMPLETARON SATISFACTORIAMENTE ===")
    print("======================================================================")

if __name__ == "__main__":
    run_test()
