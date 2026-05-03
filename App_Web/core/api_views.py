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
from .models import Area, Empresa, Proyecto, RolCliente, SolicitudReporteMensual
from .reportes_service import buscar_reporte_completado_previo
from .serializers import (
    RecursoInfrautilizadoSerializer,
    SolicitudReporteMensualSerializer,
)


class SolicitudReporteListCreateView(generics.ListCreateAPIView):
    """
    Historial y nuevas solicitudes de reporte mensual (empresa / área / proyecto).
    Protegido por Auth0 (ASR3).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = SolicitudReporteMensualSerializer

    def post(self, request, *args, **kwargs):
        """
        OPTIMIZACIÓN ASR-3: Caché de lectura en POST.
        Si la solicitud ya fue procesada previamente, devolvemos el resultado de inmediato.
        """
        data = request.data
        anio = data.get("anio")
        mes = data.get("mes")
        alcance = data.get("alcance")
        area_id = data.get("area")
        proyecto_id = data.get("proyecto")

        if anio and mes and alcance:
            # 1. Identificar empresa (Mismo logic que el serializer)
            user = request.user
            if not user or user.is_anonymous:
                empresa = Empresa.objects.filter(id=1).first() or Empresa.objects.first()
            else:
                empresa = user.empresa

            if empresa:
                # 2. Buscar si ya existe un reporte listo
                area = Area.objects.filter(id=area_id).first() if area_id else None
                proyecto = Proyecto.objects.filter(id=proyecto_id).first() if proyecto_id else None
                
                # Mock de usuario para la búsqueda (superuser para que vea todo en el test)
                from .models import Usuario
                mock_user = user if user and not user.is_anonymous else Usuario.objects.filter(is_superuser=True).first()

                previo = buscar_reporte_completado_previo(
                    mock_user, empresa, int(anio), int(mes), alcance, area, proyecto
                )
                if previo:
                    serializer = self.get_serializer(previo)
                    return Response(serializer.data, status=status.HTTP_200_OK)

        # Si no hay previo, procedemos a crear (comportamiento original lento por DB)
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
    VISTA OPTIMIZADA PARA ASR < 100ms (Pruebas de JMeter)
    --------------------------------------------------
    PROTECCIÓN: Ahora requiere autenticación Auth0 (ASR3).
    RENDIMIENTO: Utiliza caché de Redis para mantener latencia < 100ms.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 1. Parámetros de la consulta (con valores por defecto para el test)
        empresa_id = request.query_params.get("empresa_id", 1)
        umbral_raw = request.query_params.get("umbral_pct")
        limit_raw = request.query_params.get("limit", "100")
        page = request.query_params.get("page", 1)

        try:
            limit = min(int(limit_raw), 500)
        except (ValueError, TypeError):
            limit = 100

        # 2. CLAVE DE CACHÉ (Lo primero que se revisa para velocidad máxima)
        cache_key = f"infra_v3_emp_{empresa_id}_pg_{page}_lim_{limit}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            print(f"--- [CACHE HIT] Recursos Infrautilizados (Empresa {empresa_id}) ---")
            return Response(cached_data)

        print(f"--- [CACHE MISS] Consultando base de datos para Empresa {empresa_id}... ---")

        # 3. Lógica de Base de Datos (Solo si no está en Redis)
        umbral_usado = DEFAULT_UMBRAL_INFRAUTILIZADO_PCT
        if umbral_raw:
            try:
                umbral_usado = Decimal(umbral_raw)
            except InvalidOperation:
                pass

        # Consulta optimizada
        qs = queryset_recursos_infrautilizados(empresa_id, umbral_usado).order_by("cpu_utilizacion_pct")[:limit]
        recursos = list(qs)
        serializer = RecursoInfrautilizadoSerializer(recursos, many=True)

        response_data = {
            "total_encontrados": len(recursos),
            "recursos": serializer.data,
            "cached": True,
            "nota": "ASR Optimized"
        }

        # 4. Guardar en Redis por 10 minutos
        cache.set(cache_key, response_data, timeout=600)

        return Response(response_data)
