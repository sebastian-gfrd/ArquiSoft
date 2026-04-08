from django.urls import path
from django.http import JsonResponse
from .api_views import RecursosInfrautilizadosView, SolicitudReporteListCreateView
from .views import health

def api_index(request):
    return JsonResponse({
        "mensaje": "Bienvenido a la API de BITE.co - Despliegue AWS",
        "endpoints_disponibles": {
            "Desempeño (Recursos)": "/api/v1/analisis/recursos-infrautilizados/",
            "Escalabilidad (Reportes)": "/api/v1/reportes/mensuales/",
            "Admin": "/admin/",
            "Salud": "/health/"
        }
    })

urlpatterns = [
    path("", api_index, name="api-index"),  # <--- Esta es la nueva línea
    path("health/", health, name="health"),
    path("api/v1/reportes/mensuales/", SolicitudReporteListCreateView.as_view(), name="api-reportes-mensuales"),
    path("api/v1/analisis/recursos-infrautilizados/", RecursosInfrautilizadosView.as_view(), name="api-recursos-infrautilizados"),
]

