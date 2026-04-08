import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (
    Area,
    Consumo,
    Costo,
    Divisa,
    Empresa,
    Estado,
    Metricas,
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
    help = "Población masiva para pruebas de Escalabilidad y Desempeño (ASR)."

    def add_arguments(self, parser):
        parser.add_argument("--recursos", type=int, default=15000)
        parser.add_argument("--costos", type=int, default=50000)
        parser.add_argument("--admin-pass", type=str, default="admin123")
        parser.add_argument("--user-pass", type=str, default="demo123")

    def handle(self, *args, **options):
        n_recursos = options["recursos"]
        n_costos = options["costos"]
        admin_pass = options["admin_pass"]
        user_pass = options["user_pass"]

        self.stdout.write("Iniciando población de datos...")

        with transaction.atomic():
            # 1. Superusuario
            admin_user, created = Usuario.objects.get_or_create(
                email="admin@bite.test",
                defaults={
                    "nombre": "Administrador",
                    "is_staff": True,
                    "is_superuser": True,
                },
            )
            admin_user.set_password(admin_pass)
            admin_user.save()
            if created:
                self.stdout.write(f"Superusuario creado: admin@bite.test / {admin_pass}")

            # 2. Estructura de Empresa
            empresa, _ = Empresa.objects.get_or_create(
                nombre="Corporación Global Demo",
                defaults={"tipo_empresa": "Holding"},
            )
            area, _ = Area.objects.get_or_create(
                empresa=empresa,
                nombre="TI / Infraestructura",
            )
            proyecto, _ = Proyecto.objects.get_or_create(
                area=area,
                nombre="Proyecto Cloud Ready",
            )
            prov_aws, _ = ProveedorCloud.objects.get_or_create(
                empresa=empresa,
                nombre=Proveedores.AWS,
            )

            # 3. Usuario de Prueba (Ejecutivo)
            test_user, created = Usuario.objects.get_or_create(
                email="cliente.demo@bite.test",
                defaults={
                    "nombre": "Ejecutivo Demo",
                    "empresa": empresa,
                    "rol_cliente": RolCliente.EJECUTIVO_EMPRESA,
                },
            )
            test_user.set_password(user_pass)
            test_user.save()
            if created:
                self.stdout.write(f"Usuario demo creado: cliente.demo@bite.test / {user_pass}")

            # 4. Recursos Cloud (15,000)
            self.stdout.write(f"Creando {n_recursos} recursos...")
            # Limpiar anteriores para evitar duplicados en pruebas
            RecursoCloud.objects.filter(proyecto=proyecto).delete()
            
            recursos: list[RecursoCloud] = []
            for i in range(n_recursos):
                # Mezcla de infrautilizados (<20%) y normales
                if random.random() < 0.4:
                    cpu = Decimal(str(round(random.uniform(2, 19.9), 2)))
                else:
                    cpu = Decimal(str(round(random.uniform(20, 95), 2)))
                
                recursos.append(
                    RecursoCloud(
                        proyecto=proyecto,
                        proveedor=prov_aws,
                        nombre=f"srv-prod-{i:05d}",
                        tipo=random.choice(TipoRecurso.values),
                        estado=Estado.ACTIVO,
                        cpu_utilizacion_pct=cpu,
                    )
                )
            RecursoCloud.objects.bulk_create(recursos, batch_size=1000)
            
            # Recuperar IDs para crear costos
            recurso_ids = list(RecursoCloud.objects.filter(proyecto=proyecto).values_list("id", flat=True))

            # 5. Métricas para enganchar consumos (sin métricas no hay consumos/costos)
            # Reutilizamos un Análisis dummy para esto
            from core.models import Reporte, Notificacion, Analisis
            notific, _ = Notificacion.objects.get_or_create(
                usuario=admin_user,
                asunto="Pre-seed",
                defaults={"fecha_notificacion": timezone.now(), "contenido": "..."}
            )
            reporte, _ = Reporte.objects.get_or_create(
                notificacion=notific,
                titulo="Seed Data",
                defaults={"fecha": timezone.now(), "nivel": "alta"}
            )
            analisis, _ = Analisis.objects.get_or_create(
                reporte=reporte,
                defaults={"fecha": timezone.now(), "duracion": timedelta(seconds=1)}
            )
            metrica_cpu, _ = Metricas.objects.get_or_create(analisis=analisis, titulo="CPU Avg")

            # 6. Costos (50,000)
            self.stdout.write(f"Creando {n_costos} registros de costo...")
            costos: list[Costo] = []
            consumos: list[Consumo] = []
            
            hoy = date.today()
            mes_actual = hoy.replace(day=1)
            mes_anterior = (mes_actual - timedelta(days=1)).replace(day=1)

            # Para que el bulk_create de Costo funcione, primero necesitamos los Consumos
            # Como Consumo y Costo son 1:1, creamos lotes
            for i in range(n_costos):
                rid = random.choice(recurso_ids)
                c = Consumo(recurso_id=rid, metrica=metrica_cpu, valor="0")
                consumos.append(c)

            Consumo.objects.bulk_create(consumos, batch_size=1000)
            # Recuperamos los consumos recién creados (id range)
            consumo_ids = list(Consumo.objects.filter(recurso_id__in=recurso_ids).values_list("id", flat=True))
            
            for i, cid in enumerate(consumo_ids):
                fecha = mes_actual if random.random() > 0.3 else mes_anterior
                monto = Decimal(str(round(random.uniform(0.05, 50.0), 2)))
                costos.append(
                    Costo(
                        consumo_id=cid,
                        area=area,
                        fecha=fecha,
                        monto=monto,
                        divisa=Divisa.USD,
                    )
                )
                if len(costos) >= 2000:
                    Costo.objects.bulk_create(costos)
                    costos = []
            
            if costos:
                Costo.objects.bulk_create(costos)

        self.stdout.write(self.style.SUCCESS("¡Población completada con éxito!"))
        self.stdout.write(f"Acceso con: admin@bite.test (pass: {admin_pass})")
        self.stdout.write(f"O usuario cliente: cliente.demo@bite.test (pass: {user_pass})")
