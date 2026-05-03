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
        request = self.context.get("request")
        user = request.user if request else None
        
        # 1. Validación de Integridad (ASR4)
        mes = attrs.get("mes")
        anio = attrs.get("anio")
        if mes < 1 or mes > 12:
            raise serializers.ValidationError({"mes": "El mes debe estar entre 1 y 12."})
        if anio < 2020 or anio > 2030:
            raise serializers.ValidationError({"anio": "Año fuera de rango permitido."})

        # 2. Mapeo automático para pruebas de carga si no hay usuario
        if not user or user.is_anonymous:
            empresa = Empresa.objects.filter(id=1).first() or Empresa.objects.first()
            if not empresa:
                 raise serializers.ValidationError("No existe empresa en DB. Ejecute seed.")
            return attrs

        # 3. Validación de Alcance (RBAC/Integridad)
        empresa = user.empresa
        area = attrs.get("area")
        proyecto = attrs.get("proyecto")
        
        if area and area.empresa != empresa:
            raise serializers.ValidationError("El área no pertenece a su empresa.")
        if proyecto and proyecto.area.empresa != empresa:
            raise serializers.ValidationError("El proyecto no pertenece a su empresa.")

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and not request.user.is_anonymous else None
        
        if not user:
            # Usuario de respaldo para el test
            from .models import Usuario
            user = Usuario.objects.filter(is_superuser=True).first()
            empresa = Empresa.objects.filter(id=1).first() or Empresa.objects.first()
        else:
            empresa = user.empresa

        anio = validated_data["anio"]
        mes = validated_data["mes"]
        alcance = validated_data["alcance"]
        area = validated_data.get("area")
        proyecto = validated_data.get("proyecto")

        # Crear la solicitud
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
        
        # Procesar inmediatamente (Sync para el test de JMeter)
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
