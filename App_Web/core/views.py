from django.http import JsonResponse

def health(request):
    """
    Health Check de prueba (VACÍO) para diagnosticar latencia.
    """
    return JsonResponse({"status": "ok", "note": "Prueba de velocidad (sin DB/Redis)"}, status=200)
