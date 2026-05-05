from django.urls import path
from django.http import JsonResponse
from .api_views import RecursosInfrautilizadosView, SolicitudReporteListCreateView
from .views import health, index
from . import auth_views

urlpatterns = [
    path("", index, name="api-index"),
    path("health/", health, name="health"),
    path("login/", auth_views.login, name="login"),
    path("callback/", auth_views.callback, name="callback"),
    path("logout/", auth_views.logout, name="logout"),
    path("api/v1/reportes/mensuales/", SolicitudReporteListCreateView.as_view(), name="api-reportes-mensuales"),
    path("api/v1/analisis/recursos-infrautilizados/", RecursosInfrautilizadosView.as_view(), name="api-recursos-infrautilizados"),
]

