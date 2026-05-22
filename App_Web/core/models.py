from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


# --- Enumeraciones / TextChoices ---

class EstadoTenant(models.TextChoices):
    ACTIVO = "activo", "Activo"
    SUSPENDIDO = "suspendido", "Suspendido"
    INACTIVO = "inactivo", "Inactivo"


class PlanTenant(models.TextChoices):
    FREE = "free", "Free"
    PREMIUM = "premium", "Premium"
    ENTERPRISE = "enterprise", "Enterprise"


class ProveedorCloud(models.TextChoices):
    AWS = "AWS", "AWS"
    GCP = "GCP", "GCP"


class RolUserProfile(models.TextChoices):
    ADMIN = "admin", "Admin"
    VIEWER = "viewer", "Viewer"


# --- Modelos del Negocio Administrativo ---

class Tenant(models.Model):
    """
    Representa una empresa cliente (Multitenant).
    Mantiene aislamiento total a nivel de datos.
    """
    nombre = models.CharField(max_length=255, verbose_name="Nombre de la empresa")
    estado = models.CharField(
        max_length=32,
        choices=EstadoTenant.choices,
        default=EstadoTenant.ACTIVO,
        verbose_name="Estado de la empresa"
    )
    plan = models.CharField(
        max_length=32,
        choices=PlanTenant.choices,
        default=PlanTenant.FREE,
        verbose_name="Plan de suscripción"
    )
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")

    class Meta:
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
        ordering = ["-creado_en"]

    def __str__(self) -> str:
        return self.nombre


class Project(models.Model):
    """
    Representa proyectos específicos creados dentro de la frontera lógica de un Tenant.
    """
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="projects",
        verbose_name="Tenant asociado"
    )
    nombre = models.CharField(max_length=255, verbose_name="Nombre del proyecto")
    descripcion = models.TextField(blank=True, verbose_name="Descripción del proyecto")
    proveedor_cloud_primario = models.CharField(
        max_length=16,
        choices=ProveedorCloud.choices,
        default=ProveedorCloud.AWS,
        verbose_name="Proveedor Cloud Primario"
    )

    class Meta:
        verbose_name = "Project"
        verbose_name_plural = "Projects"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.tenant.nombre})"


# --- Custom User Model para Auth0 ---

class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("El correo electrónico es obligatorio.")
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
            raise ValueError("El superusuario debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("El superusuario debe tener is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class Usuario(AbstractUser):
    """
    Modelo de Usuario principal para el inicio de sesión vía Auth0.
    Se utiliza el correo electrónico como identificador único principal.
    """
    username = None
    email = models.EmailField("correo", unique=True)
    nombre = models.CharField("nombre", max_length=255)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nombre"]

    objects = UsuarioManager()

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self) -> str:
        return self.nombre


class UserProfile(models.Model):
    """
    Extensión del usuario autenticado por Auth0 que vincula
    al Usuario con su Tenant y su nivel de autorización (Rol).
    """
    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Usuario"
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="profiles",
        verbose_name="Tenant asociado"
    )
    rol = models.CharField(
        max_length=32,
        choices=RolUserProfile.choices,
        default=RolUserProfile.VIEWER,
        verbose_name="Rol de acceso"
    )

    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuarios"

    def __str__(self) -> str:
        return f"{self.usuario.email} - {self.rol} ({self.tenant.nombre})"
