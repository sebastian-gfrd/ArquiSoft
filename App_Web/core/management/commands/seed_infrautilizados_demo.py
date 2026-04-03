"""
Crea empresa demo, usuario cliente y recursos cloud con mezcla de utilización de CPU
para probar GET /api/v1/analisis/recursos-infrautilizados/ (p. ej. con JMeter).

Ejemplo:
  python manage.py seed_infrautilizados_demo --recursos 2000 --password demo123
"""

import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    Area,
    Empresa,
    Estado,
    ProveedorCloud,
    Proveedores,
    Proyecto,
    RecursoCloud,
    Rol,
    RolCliente,
    TipoRecurso,
    Usuario,
)


class Command(BaseCommand):
    help = "Pobla datos mínimos para pruebas de recursos infrautilizados."

    def add_arguments(self, parser):
        parser.add_argument(
            "--recursos",
            type=int,
            default=500,
            help="Cantidad de filas RecursoCloud a crear (aprox. 40%% bajo umbral).",
        )
        parser.add_argument(
            "--email",
            type=str,
            default="cliente.demo@bite.test",
            help="Correo del usuario cliente (se crea o actualiza contraseña).",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="demo123",
            help="Contraseña del usuario demo.",
        )

    def handle(self, *args, **options):
        n = max(1, options["recursos"])
        email = options["email"]
        password = options["password"]

        with transaction.atomic():
            empresa, _ = Empresa.objects.get_or_create(
                nombre="Empresa demo carga",
                defaults={"tipo_empresa": "Cliente"},
            )
            area, _ = Area.objects.get_or_create(
                empresa=empresa,
                nombre="Área demo",
                defaults={"descripcion": ""},
            )
            proyecto, _ = Proyecto.objects.get_or_create(
                area=area,
                nombre="Proyecto demo",
                defaults={"descripcion": ""},
            )
            prov, _ = ProveedorCloud.objects.get_or_create(
                empresa=empresa,
                nombre=Proveedores.AWS,
            )

            user, created = Usuario.objects.get_or_create(
                email=email,
                defaults={
                    "nombre": "Cliente demo",
                    "rol": Rol.EQUIPO_TECNICO,
                    "empresa": empresa,
                    "rol_cliente": RolCliente.EJECUTIVO_EMPRESA,
                },
            )
            if not created:
                user.empresa = empresa
                user.rol_cliente = RolCliente.EJECUTIVO_EMPRESA
                user.save(update_fields=["empresa", "rol_cliente"])
            user.set_password(password)
            user.save(update_fields=["password"])

            RecursoCloud.objects.filter(proyecto=proyecto).delete()

            batch: list[RecursoCloud] = []
            batch_size = 400
            for i in range(n):
                # ~40 % infrautilizados (< 20 %), resto por encima del umbral
                if random.random() < 0.4:
                    cpu = Decimal(str(round(random.uniform(0, 19.9), 2)))
                else:
                    cpu = Decimal(str(round(random.uniform(20, 99.9), 2)))
                batch.append(
                    RecursoCloud(
                        proyecto=proyecto,
                        proveedor=prov,
                        nombre=f"instancia-demo-{i}",
                        tipo=TipoRecurso.COMPUTO,
                        estado=Estado.ACTIVO,
                        cpu_utilizacion_pct=cpu,
                    )
                )
                if len(batch) >= batch_size:
                    RecursoCloud.objects.bulk_create(batch)
                    batch.clear()
            if batch:
                RecursoCloud.objects.bulk_create(batch)

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo: empresa id={empresa.pk}, usuario={email!r}, "
                f"{n} recursos en proyecto demo. Contraseña actualizada."
            )
        )
