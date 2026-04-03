"""
Consulta de recursos infrautilizados (baja utilización de CPU en instancias activas).

Criterio de laboratorio (ajustable): recurso en estado ``activo`` con
``cpu_utilizacion_pct`` estrictamente por debajo de un umbral (por defecto 20 %).
Los valores suelen provenir de la ingesta de monitoreo (AWS/GCP); aquí se
denormalizan en ``RecursoCloud`` para consultas rápidas en pruebas de carga.
"""

from decimal import Decimal

from django.db.models import QuerySet

from .models import Estado, RecursoCloud

DEFAULT_UMBRAL_INFRAUTILIZADO_PCT = Decimal("20")


def queryset_recursos_infrautilizados(
    empresa_id: int,
    umbral_pct: Decimal | None = None,
) -> QuerySet[RecursoCloud]:
    umbral = (
        umbral_pct
        if umbral_pct is not None
        else DEFAULT_UMBRAL_INFRAUTILIZADO_PCT
    )
    return (
        RecursoCloud.objects.filter(
            proyecto__area__empresa_id=empresa_id,
            estado=Estado.ACTIVO,
            cpu_utilizacion_pct__isnull=False,
            cpu_utilizacion_pct__lt=umbral,
        )
        .select_related("proyecto", "proyecto__area", "proveedor")
        .only(
            "id",
            "nombre",
            "tipo",
            "estado",
            "cpu_utilizacion_pct",
            "proyecto_id",
            "proveedor_id",
            "proyecto__nombre",
            "proyecto__area__nombre",
            "proveedor__nombre",
        )
        .order_by("cpu_utilizacion_pct", "id")
    )
