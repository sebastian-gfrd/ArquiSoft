from django.urls import path

from .api_views import RecursosInfrautilizadosView, SolicitudReporteListCreateView
from .views import health

urlpatterns = [
    path("health/", health, name="health"),
    path(
        "api/v1/reportes/mensuales/",
        SolicitudReporteListCreateView.as_view(),
        name="api-reportes-mensuales",
    ),
    path(
        "api/v1/analisis/recursos-infrautilizados/",
        RecursosInfrautilizadosView.as_view(),
        name="api-recursos-infrautilizados",
    ),
]
