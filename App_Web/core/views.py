import time
from django.db import connection
from django.core.cache import cache
from django.http import JsonResponse

def health(request):
    """
    Health Check Proactivo para ASR2 (Disponibilidad).
    Verifica que la app, la DB y Redis estén operativos.
    """
    start_time = time.time()
    checks = {
        "status": "ok",
        "database": "ok",
        "cache": "ok",
        "details": {}
    }
    
    # 1. Verificar Base de Datos
    db_start = time.time()
    try:
        connection.ensure_connection()
        checks["details"]["db_time_ms"] = round((time.time() - db_start) * 1000, 2)
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        checks["status"] = "error"

    # 2. Verificar Redis
    redis_start = time.time()
    try:
        # Usamos SOCKET_TIMEOUT corto para no colgar el balanceador
        cache.set("_health_check", "ok", timeout=5)
        if cache.get("_health_check") != "ok":
            raise Exception("Redis no devolvió el valor esperado")
        checks["details"]["redis_time_ms"] = round((time.time() - redis_start) * 1000, 2)
    except Exception as e:
        checks["cache"] = f"error: {str(e)}"
        checks["status"] = "error"

    total_time = round((time.time() - start_time) * 1000, 2)
    checks["total_time_ms"] = total_time
    
    # Log para gunicorn.log
    print(f"[HEALTH] Status: {checks['status']} | Total: {total_time}ms | DB: {checks['details'].get('db_time_ms')}ms | Redis: {checks['details'].get('redis_time_ms')}ms")

    status_code = 200 if checks["status"] == "ok" else 503
    return JsonResponse(checks, status=status_code)
