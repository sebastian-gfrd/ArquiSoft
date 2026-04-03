from rest_framework import serializers

from .models import (
    AlcanceReporte,
    Area,
    Empresa,
    Proyecto,
    RecursoCloud,
    SolicitudReporteMensual,
    Usuario,
)
from .reportes_service import (
    buscar_reporte_completado_previo,
    mes_en_curso,
    procesar_solicitud_reporte,
    usuario_puede_alcance,
)


class SolicitudReporteMensualSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitudReporteMensual
        extra_kwargs = {
            "area": {"required": False, "allow_null": True},
            "proyecto": {"required": False, "allow_null": True},
        }
        read_only_fields = (
            "id",
            "estado",
            "monto_total",
            "desglose",
            "creado_en",
            "actualizado_en",
            "periodo_parcial",
        )
        fields = read_only_fields + (
            "anio",
            "mes",
            "alcance",
            "area",
            "proyecto",
        )

    def validate(self, attrs):
        user: Usuario = self.context["request"].user
        empresa: Empresa | None = user.empresa
        if empresa is None and not (user.is_staff or user.is_superuser):
            raise serializers.ValidationError(
                "Solo usuarios asociados a una empresa cliente pueden solicitar reportes."
            )
        if user.is_staff or user.is_superuser:
            raise serializers.ValidationError(
                "Use el panel de administración o asigne una empresa al usuario de prueba."
            )
        alcance = attrs["alcance"]
        area = attrs.get("area")
        proyecto = attrs.get("proyecto")
        if area is not None and area.empresa_id != empresa.id:
            raise serializers.ValidationError({"area": "El área no pertenece a su empresa."})
        if proyecto is not None and proyecto.area.empresa_id != empresa.id:
            raise serializers.ValidationError(
                {"proyecto": "El proyecto no pertenece a su empresa."}
            )
        if alcance == AlcanceReporte.EMPRESA:
            if area is not None or proyecto is not None:
                raise serializers.ValidationError(
                    "Para alcance empresa no envíe área ni proyecto."
                )
        elif alcance == AlcanceReporte.AREA:
            if area is None:
                raise serializers.ValidationError({"area": "Requerido para alcance área."})
            if proyecto is not None:
                raise serializers.ValidationError(
                    {"proyecto": "No envíe proyecto cuando el alcance es área."}
                )
        elif alcance == AlcanceReporte.PROYECTO:
            if proyecto is None:
                raise serializers.ValidationError(
                    {"proyecto": "Requerido para alcance proyecto."}
                )
        if not usuario_puede_alcance(user, empresa, alcance, area, proyecto):
            raise serializers.ValidationError(
                "No está autorizado para este alcance de reporte (acceso interno restringido)."
            )
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        user: Usuario = request.user
        empresa = user.empresa
        assert empresa is not None
        anio = validated_data["anio"]
        mes = validated_data["mes"]
        alcance = validated_data["alcance"]
        area: Area | None = validated_data.get("area")
        proyecto: Proyecto | None = validated_data.get("proyecto")

        previo = buscar_reporte_completado_previo(
            user, empresa, anio, mes, alcance, area, proyecto
        )
        if previo is not None:
            previo._reutilizado_historial = True  # noqa: SLF001
            return previo

        solicitud = SolicitudReporteMensual.objects.create(
            usuario=user,
            empresa=empresa,
            anio=anio,
            mes=mes,
            alcance=alcance,
            area=area,
            proyecto=proyecto,
            periodo_parcial=mes_en_curso(anio, mes),
        )
        solicitud._reutilizado_historial = False  # noqa: SLF001
        procesar_solicitud_reporte(solicitud)
        solicitud.refresh_from_db()
        return solicitud


class RecursoInfrautilizadoSerializer(serializers.ModelSerializer):
    proyecto_nombre = serializers.CharField(source="proyecto.nombre", read_only=True)
    area_nombre = serializers.CharField(source="proyecto.area.nombre", read_only=True)
    proveedor = serializers.CharField(source="proveedor.nombre", read_only=True)

    class Meta:
        model = RecursoCloud
        fields = (
            "id",
            "nombre",
            "tipo",
            "estado",
            "cpu_utilizacion_pct",
            "proyecto_id",
            "proyecto_nombre",
            "area_nombre",
            "proveedor",
        )
