import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("analytics_db_worker")

# URL de conexión asíncrona a la base de datos PostgreSQL de analítica.
# Pasa a través del RDS Proxy en AWS.
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://postgres:postgres@localhost:5432/analytics"
)

logger.info(f"[DB CONFIG] Configurando conexión a base de datos. URL base presente: {'Sí' if DATABASE_URL else 'No'}")

# Configuración del pool de conexiones optimizado para AWS ECS Fargate + RDS Proxy
# pool_size=5: Controla el número de conexiones por worker para no saturar RDS Proxy
# max_overflow=10: Permite absorber picos temporales de procesamiento masivo
# pool_pre_ping=True: Verifica la conexión antes de despachar consultas (evita fallos de socket)
# pool_recycle=1800: Evita problemas con timeouts de firewall cerrando conexiones viejas (30 min)
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
    pool_pre_ping=True,
    pool_timeout=30
)

# Constructor de sesiones asíncronas
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

async def get_db_session() -> AsyncSession:
    """
    Generador asíncrono para obtener y liberar sesiones de base de datos.
    Asegura rollback automático si ocurre un error inesperado.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"[DB ERROR] Error en sesión de base de datos del Worker: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()
