"""
Modelo de dominio BITE.co alineado con el diagrama UML (paquetes Usuarios, Entorno Cloud,
Monitoreo de consumos, Reportes, Notificaciones).

Notas de modelado:
- Los tipos Long del diagrama se mapean a BigAutoField (PK por defecto en Django 5).
- ``contraseña`` del diagrama corresponde al campo ``password`` heredado de AbstractUser
  (almacenamiento con hash; no guardar texto plano).
- ``correo`` se usa como identificador de inicio de sesión (USERNAME_FIELD).
- ``duracion`` (Timestamp en UML) se modela como DurationField.
"""

from datetime import timedelta

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models


# --- Enumeraciones (TextChoices) ---


class Rol(models.TextChoices):
    """Roles internos BITE.co (CEO, CTO, COO, equipos)."""

    CEO = "ceo", "CEO"
    CTO = "cto", "CTO"
    COO = "coo", "COO"
    PO = "po", "PO"
    EQUIPO_TECNICO = "equipo_tecnico", "Equipo Técnico"
    OPERACION_Y_SOPORTE = "operacion_y_soporte", "Operación y Soporte"


class RolCliente(models.TextChoices):
    """
    Nivel de autorización dentro de la empresa cliente (accesos internos diferenciados).
    Un pasante no debe ver los mismos reportes agregados que un ejecutivo.
    """

    EJECUTIVO_EMPRESA = "ejecutivo_empresa", "Ejecutivo / vista empresa"
    RESPONSABLE_AREA = "responsable_area", "Responsable de área"
    RESPONSABLE_PROYECTO = "responsable_proyecto", "Responsable de proyecto"
    COLABORADOR_LIMITADO = "colaborador_limitado", "Colaborador (alcance restringido)"


class Divisa(models.TextChoices):
    USD = "usd", "USD"
    COP = "cop", "COP"


class Nivel(models.TextChoices):
    ALTA = "alta", "Alta"
    MEDIA = "media", "Media"
    BAJA = "baja", "Baja"


class Privilegios(models.TextChoices):
    """Definido en el diagrama; sin asignación explícita a una clase en el UML recibido."""

    ALTO = "alto", "Alto"
    MEDIO = "medio", "Medio"
    BAJO = "bajo", "Bajo"


class Proveedores(models.TextChoices):
    AWS = "aws", "AWS"
    GCP = "gcp", "GCP"


class TipoRecurso(models.TextChoices):
    COMPUTO = "computo", "Cómputo"
    ALMACENAMIENTO = "almacenamiento", "Almacenamiento"
    BASE_DE_DATOS = "base_de_datos", "Base de datos"
    RED = "red", "Red"
    SEGURIDAD = "seguridad", "Seguridad"
    MONITORIO = "monitorio", "Monitorio"


class Estado(models.TextChoices):
    ACTIVO = "activo", "Activo"
    DETENIDO = "detenido", "Detenido"
    CANCELADO = "cancelado", "Cancelado"
    SUSPENDIDO = "suspendido", "Suspendido"


# --- Entorno Cloud (orden: sin dependencias de usuario/reporte) ---


class Empresa(models.Model):
    nombre = models.CharField(max_length=255)
    tipo_empresa = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"

    def __str__(self) -> str:
        return self.nombre


class ProveedorCloud(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="proveedores_cloud",
    )
    nombre = models.CharField(max_length=16, choices=Proveedores.choices)

    class Meta:
        verbose_name = "Proveedor cloud"
        verbose_name_plural = "Proveedores cloud"
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "nombre"],
                name="uniq_proveedor_por_empresa",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_nombre_display()} ({self.empresa})"


class Area(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="areas",
    )
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = "Área"
        verbose_name_plural = "Áreas"

    def __str__(self) -> str:
        return self.nombre


class Proyecto(models.Model):
    area = models.ForeignKey(
        Area,
        on_delete=models.CASCADE,
        related_name="proyectos",
    )
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = "Proyecto"
        verbose_name_plural = "Proyectos"

    def __str__(self) -> str:
        return self.nombre


class RecursoCloud(models.Model):
    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="recursos",
    )
    proveedor = models.ForeignKey(
        ProveedorCloud,
        on_delete=models.PROTECT,
        related_name="recursos",
    )
    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=32, choices=TipoRecurso.choices)
    estado = models.CharField(
        max_length=16,
        choices=Estado.choices,
        default=Estado.ACTIVO,
    )
    cpu_utilizacion_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Última utilización de CPU observada (0–100). Para análisis FinOps / recursos infrautilizados.",
    )

    class Meta:
        verbose_name = "Recurso cloud"
        verbose_name_plural = "Recursos cloud"
        indexes = [
            models.Index(fields=["proyecto", "estado"]),
            models.Index(fields=["proveedor", "tipo"]),
            models.Index(fields=["estado", "cpu_utilizacion_pct"]),
        ]

    def __str__(self) -> str:
        return self.nombre


# --- Usuarios ---


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("El correo es obligatorio.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superusuario debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusuario debe tener is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class Usuario(AbstractUser):
    """
    ``idUser`` → PK implícita (BigAutoField).
    ``correo`` → email (USERNAME_FIELD).
    ``contraseña`` → password (AbstractUser).
    Varios usuarios pueden compartir un mismo ``Reporte`` (N:1 desde Usuario hacia Reporte).

    Miembros de una empresa cliente tienen ``empresa`` y ``rol_cliente``; el alcance de datos
    se restringe con ``area_alcance`` / ``proyecto_alcance`` cuando aplica.
    """

    username = None
    email = models.EmailField("correo", unique=True)
    nombre = models.CharField(max_length=255)
    cargo = models.CharField(max_length=255, blank=True)
    rol = models.CharField(
        max_length=32,
        choices=Rol.choices,
        default=Rol.EQUIPO_TECNICO,
    )
    empresa = models.ForeignKey(
        "Empresa",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="usuarios",
        help_text="Empresa cliente a la que pertenece el usuario (vacío para personal BITE).",
    )
    rol_cliente = models.CharField(
        max_length=32,
        choices=RolCliente.choices,
        blank=True,
        help_text="Solo usuarios cliente: qué tan amplio es su vista (empresa, área o proyecto).",
    )
    area_alcance = models.ForeignKey(
        "Area",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios_con_alcance",
        help_text="Obligatorio para responsable de área (y opcional según política).",
    )
    proyecto_alcance = models.ForeignKey(
        "Proyecto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios_con_alcance",
        help_text="Obligatorio para responsable de proyecto o colaborador limitado.",
    )
    reporte = models.ForeignKey(
        "Reporte",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nombre"]

    objects = UsuarioManager()

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self) -> str:
        return self.nombre

    def clean(self):
        super().clean()
        if self.empresa_id:
            if not self.rol_cliente:
                raise ValidationError(
                    {"rol_cliente": "Los usuarios de una empresa cliente requieren rol_cliente."}
                )
            if self.rol_cliente == RolCliente.RESPONSABLE_AREA and not self.area_alcance_id:
                raise ValidationError(
                    {"area_alcance": "Defina el área para responsable de área."}
                )
            if self.rol_cliente in (
                RolCliente.RESPONSABLE_PROYECTO,
                RolCliente.COLABORADOR_LIMITADO,
            ) and not self.proyecto_alcance_id:
                raise ValidationError(
                    {"proyecto_alcance": "Defina el proyecto para este rol cliente."}
                )
            if self.area_alcance_id and self.area_alcance.empresa_id != self.empresa_id:
                raise ValidationError(
                    {"area_alcance": "El área debe pertenecer a la misma empresa."}
                )
            if self.proyecto_alcance_id and self.proyecto_alcance.area.empresa_id != self.empresa_id:
                raise ValidationError(
                    {"proyecto_alcance": "El proyecto debe pertenecer a la misma empresa."}
                )
        elif self.rol_cliente or self.area_alcance_id or self.proyecto_alcance_id:
            raise ValidationError(
                "rol_cliente y alcances solo aplican si el usuario tiene empresa asignada."
            )


class TipoEventoAcceso(models.TextChoices):
    LOGIN = "login", "Inicio de sesión"
    API = "api", "API / recurso"
    OTRO = "otro", "Otro"


class Acceso(models.Model):
    """
    Registro de accesos e intentos (incluye fallidos y denegaciones por permiso),
    alineado a detectar, bloquear y auditar accesos no autorizados.
    """

    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="accesos",
        help_text="Nulo si el intento no identifica a un usuario (p. ej. credencial inválida).",
    )
    fecha = models.DateTimeField()
    duracion = models.DurationField(
        help_text="Duración de la sesión o del evento de acceso.",
        default=timedelta(0),
    )
    tipo_evento = models.CharField(
        max_length=16,
        choices=TipoEventoAcceso.choices,
        default=TipoEventoAcceso.LOGIN,
    )
    exitoso = models.BooleanField(default=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    ruta = models.CharField(max_length=512, blank=True)
    detalle = models.TextField(blank=True)

    class Meta:
        verbose_name = "Acceso"
        verbose_name_plural = "Accesos"
        ordering = ["-fecha"]

    def __str__(self) -> str:
        u = self.usuario or "—"
        return f"Acceso {self.pk} — {u}"


class Registro(models.Model):
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="registros",
    )
    tipo = models.CharField(max_length=255)
    id_transaccion = models.BigIntegerField()

    class Meta:
        verbose_name = "Registro"
        verbose_name_plural = "Registros"

    def __str__(self) -> str:
        return f"{self.tipo} ({self.id_transaccion})"


# --- Notificaciones y Reportes (Notificacion antes que Reporte por FK 1:1) ---


class Notificacion(models.Model):
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="notificaciones",
    )
    fecha_notificacion = models.DateTimeField()
    asunto = models.CharField(max_length=255)
    contenido = models.TextField()

    class Meta:
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        ordering = ["-fecha_notificacion"]

    def __str__(self) -> str:
        return self.asunto


class Reporte(models.Model):
    """
    Relación 1:1 con Notificacion y con Analisis (desde el lado Analisis: OneToOne a Reporte).
    """

    notificacion = models.OneToOneField(
        Notificacion,
        on_delete=models.CASCADE,
        related_name="reporte",
    )
    titulo = models.CharField(max_length=255)
    fecha = models.DateTimeField()
    descripcion = models.TextField(blank=True)
    nivel = models.CharField(max_length=16, choices=Nivel.choices)

    class Meta:
        verbose_name = "Reporte"
        verbose_name_plural = "Reportes"

    def __str__(self) -> str:
        return self.titulo


# --- Monitoreo de consumos ---


class Analisis(models.Model):
    reporte = models.OneToOneField(
        Reporte,
        on_delete=models.CASCADE,
        related_name="analisis",
    )
    fecha = models.DateTimeField()
    duracion = models.DurationField(
        help_text="Duración del proceso de análisis.",
    )

    class Meta:
        verbose_name = "Análisis"
        verbose_name_plural = "Análisis"

    def __str__(self) -> str:
        return f"Análisis {self.pk}"


class Metricas(models.Model):
    analisis = models.ForeignKey(
        Analisis,
        on_delete=models.CASCADE,
        related_name="metricas",
    )
    titulo = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Métrica"
        verbose_name_plural = "Métricas"

    def __str__(self) -> str:
        return self.titulo


class Consumo(models.Model):
    recurso = models.ForeignKey(
        RecursoCloud,
        on_delete=models.CASCADE,
        related_name="consumos",
    )
    metrica = models.ForeignKey(
        Metricas,
        on_delete=models.CASCADE,
        related_name="consumos",
    )
    valor = models.CharField(max_length=512)

    class Meta:
        verbose_name = "Consumo"
        verbose_name_plural = "Consumos"
        indexes = [
            models.Index(fields=["recurso"]),
        ]

    def __str__(self) -> str:
        return f"Consumo {self.pk} ({self.recurso})"


class Costo(models.Model):
    """
    Cada costo está asociado a exactamente un Consumo (1:1).
    Muchos costos pertenecen a un Área (N:1).

    ``fecha`` permite agregar por mes para reportes mensuales (datos típicamente
    provenientes del proveedor cloud, posiblemente tras normalización mínima).
    """

    consumo = models.OneToOneField(
        Consumo,
        on_delete=models.CASCADE,
        related_name="costo",
    )
    area = models.ForeignKey(
        Area,
        on_delete=models.CASCADE,
        related_name="costos",
    )
    fecha = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha de imputación del costo (p. ej. cierre diario/mensual del proveedor).",
    )
    monto = models.DecimalField(max_digits=14, decimal_places=4)
    divisa = models.CharField(max_length=8, choices=Divisa.choices)

    class Meta:
        verbose_name = "Costo"
        verbose_name_plural = "Costos"
        indexes = [
            models.Index(fields=["area"]),
            models.Index(fields=["area", "fecha"]),
        ]

    def __str__(self) -> str:
        return f"{self.monto} {self.divisa}"


class AlcanceReporte(models.TextChoices):
    EMPRESA = "empresa", "Empresa"
    AREA = "area", "Área"
    PROYECTO = "proyecto", "Proyecto"


class EstadoSolicitudReporte(models.TextChoices):
    PENDIENTE = "pendiente", "Pendiente"
    EN_COLA = "en_cola", "En cola"
    COMPLETADO = "completado", "Completado"
    RECHAZADO_SOBRECARGA = "rechazado_sobrecarga", "Rechazado por sobrecarga"
    ERROR = "error", "Error"


class SolicitudReporteMensual(models.Model):
    """
    Solicitud e historial de reportes mensuales por empresa / área / proyecto.

    - Mes en curso: puede almacenarse como periodo parcial (gastos hasta el momento).
    - Reportes cerrados quedan en historial para consulta sin volver a generarlos.
    """

    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="solicitudes_reporte",
    )
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="solicitudes_reporte",
    )
    area = models.ForeignKey(
        Area,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="solicitudes_reporte",
    )
    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="solicitudes_reporte",
    )
    alcance = models.CharField(max_length=16, choices=AlcanceReporte.choices)
    anio = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField()
    periodo_parcial = models.BooleanField(
        default=False,
        help_text="True si el mes aún está en curso y los montos son acumulados a la fecha.",
    )
    estado = models.CharField(
        max_length=32,
        choices=EstadoSolicitudReporte.choices,
        default=EstadoSolicitudReporte.PENDIENTE,
    )
    monto_total = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    divisa = models.CharField(
        max_length=8,
        choices=Divisa.choices,
        default=Divisa.USD,
    )
    desglose = models.JSONField(
        null=True,
        blank=True,
        help_text="Detalle opcional (por servicio, proveedor, etc.) para tableros o exportación.",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Solicitud de reporte mensual"
        verbose_name_plural = "Solicitudes de reporte mensual"
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["empresa", "anio", "mes"]),
        ]

    def clean(self):
        super().clean()
        if self.alcance == AlcanceReporte.AREA and not self.area_id:
            raise ValidationError({"area": "Indique el área para el alcance área."})
        if self.alcance == AlcanceReporte.PROYECTO and not self.proyecto_id:
            raise ValidationError({"proyecto": "Indique el proyecto para el alcance proyecto."})
        if self.alcance == AlcanceReporte.EMPRESA:
            if self.area_id or self.proyecto_id:
                raise ValidationError("Para alcance empresa no debe enviar área ni proyecto.")
        if self.mes < 1 or self.mes > 12:
            raise ValidationError({"mes": "El mes debe estar entre 1 y 12."})

    def __str__(self) -> str:
        return f"{self.anio}-{self.mes:02d} {self.get_alcance_display()} ({self.estado})"
