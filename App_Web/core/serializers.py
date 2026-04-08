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
        
        # --- LÓGICA PARA PRUEBAS DE CARGA (JMeter) ---
        if not user or user.is_anonymous:
            # Si no hay usuario, verificamos que exista la empresa de prueba
            empresa = Empresa.objects.filter(id=1).first()
            if not empresa:
                 raise serializers.ValidationError("No existe la empresa de prueba (ID 1).")
            return attrs

        # --- LÓGICA PARA USUARIOS REALES ---
        empresa = user.empresa
        if empresa is None and not (user.is_staff or user.is_superuser):
            raise serializers.ValidationError(
                "Solo usuarios asociados a una empresa cliente pueden solicitar reportes."
            )
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and not request.user.is_anonymous else None
        
        if not user:
            # Usuario de respaldo para el historial durante el test
            from .models import Usuario
            user = Usuario.objects.filter(is_superuser=True).first()
            empresa = Empresa.objects.get(id=1)
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

