from decimal import Decimal, InvalidOperation

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

    - Mes en curso: ``periodo_parcial`` indica montos acumulados hasta la fecha.
    - Meses cerrados ya completados se devuelven desde historial sin regenerar.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = SolicitudReporteMensualSerializer

    def get_queryset(self):
        user = self.request.user
        qs = SolicitudReporteMensual.objects.select_related(
            "empresa", "area", "proyecto", "usuario"
        )
        if user.is_superuser:
            return qs
        if not user.empresa_id:
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
        if getattr(obj, "_reutilizado_historial", False):
            return Response(serializer.data, status=status.HTTP_200_OK, headers=headers)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class RecursosInfrautilizadosView(APIView):
    """
    Análisis de consumo: recursos activos con utilización de CPU por debajo del umbral.

    Pensado para pruebas de carga (JMeter) y cumplimiento de latencia; autenticación
    recomendada: Basic Auth (usuario cliente con ``empresa`` asignada).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        empresa_id = request.user.empresa_id
        if request.user.is_superuser:
            raw = request.query_params.get("empresa_id")
            if raw is not None:
                try:
                    empresa_id = int(raw)
                except ValueError:
                    return Response(
                        {"detail": "empresa_id inválido."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        if empresa_id is None:
            return Response(
                {"detail": "Se requiere usuario con empresa o ?empresa_id= (superusuario)."},
                status=status.HTTP_403_FORBIDDEN,
            )

        umbral_raw = request.query_params.get("umbral_pct")
        umbral_dec = None
        if umbral_raw is not None:
            try:
                umbral_dec = Decimal(umbral_raw)
            except InvalidOperation:
                return Response(
                    {"detail": "umbral_pct inválido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        qs = queryset_recursos_infrautilizados(empresa_id, umbral_dec)
        recursos = list(qs)
        serializer = RecursoInfrautilizadoSerializer(recursos, many=True)
        umbral_usado = (
            umbral_dec
            if umbral_dec is not None
            else DEFAULT_UMBRAL_INFRAUTILIZADO_PCT
        )
        return Response(
            {
                "umbral_pct": str(umbral_usado),
                "total": len(recursos),
                "recursos": serializer.data,
            }
        )
