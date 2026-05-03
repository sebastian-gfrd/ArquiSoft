from django.db import connection
from django.core.cache import cache
from django.http import JsonResponse

def health(request):
    """
    Health Check Proactivo para ASR2 (Disponibilidad).
    Verifica que la app, la DB y Redis estén operativos.
    """
    checks = {
        "status": "ok",
        "database": "ok",
        "cache": "ok"
    }
    
    # 1. Verificar Base de Datos
    try:
        connection.ensure_connection()
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        checks["status"] = "error"

    # 2. Verificar Redis
    try:
        cache.set("_health_check", "ok", timeout=5)
        if cache.get("_health_check") != "ok":
            raise Exception("Redis no devolvió el valor esperado")
    except Exception as e:
        checks["cache"] = f"error: {str(e)}"
        checks["status"] = "error"

    status_code = 200 if checks["status"] == "ok" else 503
    return JsonResponse(checks, status=status_code)
