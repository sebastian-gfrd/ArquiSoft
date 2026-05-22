import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("analytics_db")

# URL de conexión asíncrona a la base de datos PostgreSQL
# En producción se debe proveer postgresql+asyncpg://...
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://postgres:postgres@localhost:5432/analytics"
)

logger.info(f"Configurando conexión a base de datos. URL base presente: {'Sí' if DATABASE_URL else 'No'}")

# Configuración del pool de conexiones optimizado para AWS Lambda + RDS Proxy
# pool_size=5: Evita que múltiples lambdas saturen el proxy de RDS
# max_overflow=10: Permite que el pool crezca controladamente ante ráfagas
# pool_pre_ping=True: Realiza un SELECT 1 antes de entregar una conexión para evitar sockets cerrados
# pool_recycle=1800: Recicla las conexiones inactivas cada 30 minutos
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Cambiar a True para depuración de SQL
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
    Dependency para inyectar la sesión asíncrona de base de datos en los endpoints.
    Asegura la liberación correcta del socket de conexión tras finalizar la petición.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Error en sesión de base de datos: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()
