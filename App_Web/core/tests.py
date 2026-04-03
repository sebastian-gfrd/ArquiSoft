from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .models import (
    AlcanceReporte,
    Analisis,
    Area,
    Consumo,
    Costo,
    Divisa,
    Empresa,
    Estado,
    EstadoSolicitudReporte,
    Metricas,
    Notificacion,
    ProveedorCloud,
    Proyecto,
    RecursoCloud,
    Reporte,
    RolCliente,
    SolicitudReporteMensual,
    TipoRecurso,
)
from .reportes_service import usuario_puede_alcance

Usuario = get_user_model()


def _cadena_metrica_consumo(recurso):
    n = Notificacion.objects.create(
        usuario=recurso.proyecto.area.empresa.usuarios.first(),
        fecha_notificacion=timezone.now(),
        asunto="n",
        contenido="c",
    )
    rep = Reporte.objects.create(
        notificacion=n,
        titulo="r",
        fecha=timezone.now(),
        nivel="media",
    )
    an = Analisis.objects.create(
        reporte=rep,
        fecha=timezone.now(),
        duracion=timedelta(seconds=1),
    )
    m = Metricas.objects.create(analisis=an, titulo="m")
    c = Consumo.objects.create(recurso=recurso, metrica=m, valor="1")
    return c


class AlcanceInternoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre="ACME", tipo_empresa="Cliente")
        self.area = Area.objects.create(empresa=self.empresa, nombre="Finanzas")
        self.proyecto = Proyecto.objects.create(area=self.area, nombre="P1")
        self.user_ej = Usuario.objects.create_user(
            email="ej@acme.test",
            password="x",
            nombre="Ejecutivo",
            empresa=self.empresa,
            rol_cliente=RolCliente.EJECUTIVO_EMPRESA,
        )
        self.user_pas = Usuario.objects.create_user(
            email="pas@acme.test",
            password="x",
            nombre="Pasante",
            empresa=self.empresa,
            rol_cliente=RolCliente.COLABORADOR_LIMITADO,
            proyecto_alcance=self.proyecto,
        )

    def test_colaborador_no_ve_alcance_empresa(self):
        assert usuario_puede_alcance(
            self.user_ej, self.empresa, AlcanceReporte.EMPRESA, None, None
        )
        assert not usuario_puede_alcance(
            self.user_pas, self.empresa, AlcanceReporte.EMPRESA, None, None
        )

    def test_colaborador_ve_su_proyecto(self):
        assert usuario_puede_alcance(
            self.user_pas,
            self.empresa,
            AlcanceReporte.PROYECTO,
            None,
            self.proyecto,
        )


class ReporteMensualAPITests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre="ACME", tipo_empresa="Cliente")
        self.area = Area.objects.create(empresa=self.empresa, nombre="Finanzas")
        self.proyecto = Proyecto.objects.create(area=self.area, nombre="P1")
        self.proveedor = ProveedorCloud.objects.create(empresa=self.empresa, nombre="aws")
        self.recurso = RecursoCloud.objects.create(
            proyecto=self.proyecto,
            proveedor=self.proveedor,
            nombre="vm-1",
            tipo=TipoRecurso.COMPUTO,
        )
        self.user = Usuario.objects.create_user(
            email="cli@acme.test",
            password="secret",
            nombre="Cliente",
            empresa=self.empresa,
            rol_cliente=RolCliente.EJECUTIVO_EMPRESA,
        )
        consumo = _cadena_metrica_consumo(self.recurso)
        Costo.objects.create(
            consumo=consumo,
            area=self.area,
            fecha=date(2026, 2, 15),
            monto=Decimal("100.50"),
            divisa=Divisa.USD,
        )
        self.client = APIClient()
        self.client.force_login(self.user)

    def test_reporte_agrega_costos_mes(self):
        url = "/api/v1/reportes/mensuales/"
        r = self.client.post(
            url,
            {
                "anio": 2026,
                "mes": 2,
                "alcance": AlcanceReporte.EMPRESA,
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["estado"], EstadoSolicitudReporte.COMPLETADO)
        self.assertEqual(Decimal(r.data["monto_total"]), Decimal("100.50"))
        self.assertTrue(r.data["periodo_parcial"] is False)

    def test_reutiliza_historial_mes_cerrado(self):
        url = "/api/v1/reportes/mensuales/"
        body = {"anio": 2026, "mes": 2, "alcance": AlcanceReporte.EMPRESA}
        r1 = self.client.post(url, body, format="json")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        pk1 = r1.data["id"]
        r2 = self.client.post(url, body, format="json")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(r2.data["id"], pk1)

    @override_settings(BITE_SIMULAR_SOBRECARGA_REPORTES=True)
    def test_sobrecarga_crea_notificacion(self):
        from .models import Notificacion

        antes = Notificacion.objects.filter(usuario=self.user).count()
        r = self.client.post(
            "/api/v1/reportes/mensuales/",
            {"anio": 2025, "mes": 1, "alcance": AlcanceReporte.EMPRESA},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["estado"], EstadoSolicitudReporte.RECHAZADO_SOBRECARGA)
        self.assertGreater(Notificacion.objects.filter(usuario=self.user).count(), antes)


class RecursosInfrautilizadosAPITests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre="ACME", tipo_empresa="Cliente")
        self.area = Area.objects.create(empresa=self.empresa, nombre="Finanzas")
        self.proyecto = Proyecto.objects.create(area=self.area, nombre="P1")
        self.proveedor = ProveedorCloud.objects.create(empresa=self.empresa, nombre="aws")
        RecursoCloud.objects.create(
            proyecto=self.proyecto,
            proveedor=self.proveedor,
            nombre="baja-cpu",
            tipo=TipoRecurso.COMPUTO,
            estado=Estado.ACTIVO,
            cpu_utilizacion_pct="5.00",
        )
        RecursoCloud.objects.create(
            proyecto=self.proyecto,
            proveedor=self.proveedor,
            nombre="alta-cpu",
            tipo=TipoRecurso.COMPUTO,
            estado=Estado.ACTIVO,
            cpu_utilizacion_pct="90.00",
        )
        self.user = Usuario.objects.create_user(
            email="cli@acme.test",
            password="secret",
            nombre="Cliente",
            empresa=self.empresa,
            rol_cliente=RolCliente.EJECUTIVO_EMPRESA,
        )
        self.client = APIClient()

    def test_lista_solo_infrautilizados(self):
        self.client.force_login(self.user)
        r = self.client.get("/api/v1/analisis/recursos-infrautilizados/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["total"], 1)
        self.assertEqual(r.data["recursos"][0]["nombre"], "baja-cpu")

    def test_basic_auth_jmeter(self):
        r = self.client.get(
            "/api/v1/analisis/recursos-infrautilizados/",
            HTTP_AUTHORIZATION="Basic "
            + __import__("base64").b64encode(b"cli@acme.test:secret").decode(),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["total"], 1)
