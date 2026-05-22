import os
import json
import logging
from typing import Any, Optional
import redis.asyncio as aioredis

logger = logging.getLogger("analytics_cache")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

logger.info("Inicializando cliente asíncrono de Redis...")

# Cliente Redis asíncrono con pool de conexiones optimizado para ambiente serverless
# decode_responses=True decodifica automáticamente bytes a strings UTF-8.
redis_client: aioredis.Redis = aioredis.from_url(
    REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    max_connections=10,  # Límite del pool de conexiones por instancia Lambda
    socket_timeout=5.0,  # Evita bloqueos prolongados ante caídas de red
    socket_connect_timeout=5.0
)

async def get_cache(key: str) -> Optional[Any]:
    """
    Intenta obtener un valor de la caché de Redis por su clave.
    
    Tolerancia a Fallos: Si Redis no está disponible o falla, la función captura el 
    error y retorna None para que el flujo principal continúe directamente a la Base de Datos.
    """
    try:
        data = await redis_client.get(key)
        if data:
            logger.info(f"[Cache Hit] Llave encontrada en Redis: {key}")
            return json.loads(data)
        logger.info(f"[Cache Miss] Llave no encontrada en Redis: {key}")
    except Exception as e:
        # Silenciamos el error para no romper la petición HTTP (resiliencia)
        logger.error(f"[Cache Error] Falló lectura en Redis para la llave '{key}': {e}")
    return None

async def set_cache(key: str, value: Any, expire_seconds: int = 300) -> bool:
    """
    Guarda un valor serializado en JSON en la caché con un TTL (Time-To-Live).
    
    Tolerancia a Fallos: Captura excepciones para evitar degradación de la experiencia 
    de usuario si el servidor de caché tiene problemas temporales.
    """
    try:
        serialized_value = json.dumps(value)
        # Se establece la llave junto con su expiración de forma atómica
        await redis_client.set(key, serialized_value, ex=expire_seconds)
        logger.info(f"[Cache Set] Llave guardada en Redis: {key} (TTL: {expire_seconds}s)")
        return True
    except Exception as e:
        logger.error(f"[Cache Error] Falló escritura en Redis para la llave '{key}': {e}")
        return False
