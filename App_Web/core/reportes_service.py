from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone

from .models import (
    AlcanceReporte,
    Area,
    Costo,
    Empresa,
    EstadoSolicitudReporte,
    Notificacion,
    Proyecto,
    RolCliente,
    SolicitudReporteMensual,
    Usuario,
)
from .notificaciones_textos import (
    asunto_reporte_sistema_sobrecargado,
    cuerpo_reporte_sistema_sobrecargado,
)


def mes_en_curso(anio: int, mes: int) -> bool:
    hoy = timezone.localdate()
    return hoy.year == anio and hoy.month == mes


def usuario_puede_alcance(
    usuario: Usuario,
    empresa: Empresa,
    alcance: str,
    area: Area | None,
    proyecto: Proyecto | None,
) -> bool:
    if usuario.is_superuser or usuario.is_staff:
        return True
    if not usuario.empresa_id or usuario.empresa_id != empresa.id:
        return False
    rol = usuario.rol_cliente
    if rol == RolCliente.EJECUTIVO_EMPRESA:
        return True
    if rol == RolCliente.RESPONSABLE_AREA:
        if alcance == AlcanceReporte.EMPRESA:
            return False
        if alcance == AlcanceReporte.AREA:
            return area is not None and area.id == usuario.area_alcance_id
        if alcance == AlcanceReporte.PROYECTO:
            return (
                proyecto is not None
                and usuario.area_alcance_id is not None
                and proyecto.area_id == usuario.area_alcance_id
            )
    if rol in (RolCliente.RESPONSABLE_PROYECTO, RolCliente.COLABORADOR_LIMITADO):
        if alcance != AlcanceReporte.PROYECTO:
            return False
        return proyecto is not None and proyecto.id == usuario.proyecto_alcance_id
    return False


def _costos_filtrados(
    empresa: Empresa,
    anio: int,
    mes: int,
    alcance: str,
    area: Area | None,
    proyecto: Proyecto | None,
):
    qs = Costo.objects.filter(
        area__empresa=empresa,
        fecha__year=anio,
        fecha__month=mes,
    )
    if alcance == AlcanceReporte.AREA and area is not None:
        qs = qs.filter(area=area)
    if alcance == AlcanceReporte.PROYECTO and proyecto is not None:
        qs = qs.filter(consumo__recurso__proyecto=proyecto)
    return qs.distinct()


def agregar_montos(
    empresa: Empresa,
    anio: int,
    mes: int,
    alcance: str,
    area: Area | None,
    proyecto: Proyecto | None,
) -> tuple[Decimal | None, dict[str, Any]]:
    # -- Cache para Escalabilidad (Evita Thundering Herd en mes en curso) --
    es_mes_actual = mes_en_curso(anio, mes)
    cache_key = None
    if es_mes_actual:
        area_id = area.id if area else "none"
        proj_id = proyecto.id if proyecto else "none"
        cache_key = f"report_total_{empresa.id}_{anio}_{mes}_{alcance}_{area_id}_{proj_id}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return Decimal(cached_result[0]), cached_result[1]

    qs = _costos_filtrados(empresa, anio, mes, alcance, area, proyecto)
    agg = qs.aggregate(total=Sum("monto"))
    total = agg["total"]
    if total is None:
        total_dec = Decimal("0")
    else:
        total_dec = total
    por_divisa = {}
    for row in qs.values("divisa").annotate(sub=Sum("monto")):
        por_divisa[row["divisa"]] = str(row["sub"] or Decimal("0"))
    desglose: dict[str, Any] = {
        "por_divisa": por_divisa,
        "registros_costo": qs.count(),
    }

    if cache_key:
        # Cache por 5 minutos para el mes en curso (balance entre rapidez y frescura)
        cache.set(cache_key, (str(total_dec), desglose), timeout=300)

    return total_dec, desglose


def sistema_reporte_sobrecargado() -> bool:
    return bool(getattr(settings, "BITE_SIMULAR_SOBRECARGA_REPORTES", False))


def procesar_solicitud_reporte(solicitud: SolicitudReporteMensual) -> None:
    """Calcula montos y marca estado; si hay sobrecarga simulada, notifica y rechaza."""
    if sistema_reporte_sobrecargado():
        solicitud.estado = EstadoSolicitudReporte.RECHAZADO_SOBRECARGA
        solicitud.save(update_fields=["estado", "actualizado_en"])
        Notificacion.objects.create(
            usuario=solicitud.usuario,
            fecha_notificacion=timezone.now(),
            asunto=asunto_reporte_sistema_sobrecargado(),
            contenido=cuerpo_reporte_sistema_sobrecargado(solicitud.usuario.nombre),
        )
        return

    total, desglose = agregar_montos(
        solicitud.empresa,
        solicitud.anio,
        solicitud.mes,
        solicitud.alcance,
        solicitud.area,
        solicitud.proyecto,
    )
    solicitud.monto_total = total
    solicitud.desglose = desglose
    solicitud.estado = EstadoSolicitudReporte.COMPLETADO
    solicitud.save(
        update_fields=["monto_total", "desglose", "estado", "actualizado_en"]
    )


def buscar_reporte_completado_previo(
    usuario: Usuario,
    empresa: Empresa,
    anio: int,
    mes: int,
    alcance: str,
    area: Area | None,
    proyecto: Proyecto | None,
) -> SolicitudReporteMensual | None:
    """Evita regenerar lo ya cerrado: mismo periodo y alcance con resultado listo."""
    if mes_en_curso(anio, mes):
        return None
    qs = SolicitudReporteMensual.objects.filter(
        empresa=empresa,
        anio=anio,
        mes=mes,
        alcance=alcance,
        estado=EstadoSolicitudReporte.COMPLETADO,
        periodo_parcial=False,
    )
    if area is not None:
        qs = qs.filter(area=area)
    else:
        qs = qs.filter(area__isnull=True)
    if proyecto is not None:
        qs = qs.filter(proyecto=proyecto)
    else:
        qs = qs.filter(proyecto__isnull=True)
    if usuario.rol_cliente == RolCliente.EJECUTIVO_EMPRESA:
        return qs.order_by("-creado_en").first()
    return qs.filter(usuario=usuario).order_by("-creado_en").first()
