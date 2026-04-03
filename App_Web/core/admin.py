from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Acceso,
    Analisis,
    Area,
    Consumo,
    Costo,
    Empresa,
    Metricas,
    Notificacion,
    ProveedorCloud,
    Proyecto,
    RecursoCloud,
    Registro,
    Reporte,
    SolicitudReporteMensual,
    Usuario,
)


@admin.register(Usuario)
class UsuarioAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = (
        "email",
        "nombre",
        "rol",
        "empresa",
        "rol_cliente",
        "is_staff",
        "is_active",
    )
    search_fields = ("email", "nombre", "cargo")
    filter_horizontal = ("groups", "user_permissions")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Datos BITE.co",
            {
                "fields": (
                    "nombre",
                    "cargo",
                    "rol",
                    "reporte",
                    "empresa",
                    "rol_cliente",
                    "area_alcance",
                    "proyecto_alcance",
                ),
            },
        ),
        (
            "Permisos",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "nombre",
                    "password1",
                    "password2",
                    "rol",
                    "cargo",
                    "empresa",
                    "rol_cliente",
                    "area_alcance",
                    "proyecto_alcance",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )


@admin.register(Acceso)
class AccesoAdmin(admin.ModelAdmin):
    list_display = (
        "fecha",
        "tipo_evento",
        "exitoso",
        "usuario",
        "ip_address",
        "ruta",
    )
    list_filter = ("exitoso", "tipo_evento")
    search_fields = ("detalle", "ruta", "usuario__email")
admin.site.register(Analisis)
admin.site.register(Area)
admin.site.register(Consumo)
admin.site.register(Costo)
admin.site.register(Empresa)
admin.site.register(Metricas)
admin.site.register(Notificacion)
admin.site.register(ProveedorCloud)
admin.site.register(Proyecto)
admin.site.register(RecursoCloud)
admin.site.register(Registro)
admin.site.register(Reporte)


@admin.register(SolicitudReporteMensual)
class SolicitudReporteMensualAdmin(admin.ModelAdmin):
    list_display = (
        "creado_en",
        "empresa",
        "alcance",
        "anio",
        "mes",
        "estado",
        "periodo_parcial",
        "usuario",
    )
    list_filter = ("estado", "alcance", "periodo_parcial")
    search_fields = ("usuario__email", "empresa__nombre")
