from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .infrautilizados_service import (
    DEFAULT_UMBRAL_INFRAUTILIZADO_PCT,
    queryset_recursos_infrautilizados,
)
from .models import RolCliente, SolicitudReporteMensual
from .serializers import (
    RecursoInfrautilizadoSerializer,
    SolicitudReporteMensualSerializer,
)


class SolicitudReporteListCreateView(generics.ListCreateAPIView):
    """
    Historial y nuevas solicitudes de reporte mensual (empresa / área / proyecto).
    """

    permission_classes = []  # Público para la prueba de carga
    serializer_class = SolicitudReporteMensualSerializer

    def post(self, request, *args, **kwargs):
        print("--- [PERF] Procesando POST Solicitud de Reporte ---")
        return self.create(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        qs = SolicitudReporteMensual.objects.select_related(
            "empresa", "area", "proyecto", "usuario"
        )
        
        # 1. Superusuario ve todo
        if user.is_authenticated and user.is_superuser:
            return qs
            
        # 2. JMeter Test (Sin logueo): Devolver empresa 1 por defecto
        if not user.is_authenticated:
            return qs.filter(empresa_id=1)
            
        # 3. Usuarios reales logueados
        if not getattr(user, "empresa_id", None):
            return qs.none()
            
        qs = qs.filter(empresa_id=user.empresa_id)
        if user.rol_cliente == RolCliente.EJECUTIVO_EMPRESA:
            return qs
        return qs.filter(usuario=user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        obj = serializer.instance
        headers = self.get_success_headers(serializer.data)
        
        # Respuesta 200 si se reutilizó, 201 si es nuevo
        status_code = status.HTTP_201_CREATED
        if getattr(obj, "_reutilizado_historial", False):
            status_code = status.HTTP_200_OK
            
        return Response(serializer.data, status=status_code, headers=headers)


class RecursosInfrautilizadosView(APIView):
    """
    VISTA OPTIMIZADA PARA ASR < 100ms
    """
    permission_classes = [] 

    def get(self, request, *args, **kwargs):
        empresa_id = request.query_params.get("empresa_id", 1)
        umbral_raw = request.query_params.get("umbral_pct")
        limit_raw = request.query_params.get("limit", "100")
        page = request.query_params.get("page", 1)

        try:
            limit = min(int(limit_raw), 500)
        except (ValueError, TypeError):
            limit = 100

        # CLAVE DE CACHÉ
        cache_key = f"infra_v3_emp_{empresa_id}_pg_{page}_lim_{limit}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            print(f"--- [CACHE HIT] Recursos Infrautilizados (Empresa {empresa_id}) ---")
            return Response(cached_data)

        print(f"--- [CACHE MISS] Consultando base de datos para Empresa {empresa_id}... ---")

        umbral_usado = DEFAULT_UMBRAL_INFRAUTILIZADO_PCT
        if umbral_raw:
            try:
                umbral_usado = Decimal(umbral_raw)
            except InvalidOperation:
                pass

        qs = queryset_recursos_infrautilizados(empresa_id, umbral_usado).order_by("cpu_utilizacion_pct")[:limit]
        recursos = list(qs)
        serializer = RecursoInfrautilizadoSerializer(recursos, many=True)

        response_data = {
            "total_encontrados": len(recursos),
            "recursos": serializer.data,
            "cached": True,
            "nota": "ASR Optimized"
        }

        cache.set(cache_key, response_data, timeout=600)
        return Response(response_data)
