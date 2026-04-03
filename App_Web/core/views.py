from django.http import JsonResponse


def health(request):
    """Sin autenticación: para health checks del balanceador (ALB) en AWS."""
    return JsonResponse({"status": "ok"})
