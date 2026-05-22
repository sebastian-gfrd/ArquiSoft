from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import Usuario, Tenant, Project, UserProfile


@admin.register(Usuario)
class UsuarioAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = (
        "email",
        "nombre",
        "is_staff",
        "is_active",
    )
    search_fields = ("email", "nombre")
    filter_horizontal = ("groups", "user_permissions")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Datos Personales",
            {
                "fields": ("nombre",),
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
                    "password",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("nombre", "estado", "plan", "creado_en")
    list_filter = ("estado", "plan")
    search_fields = ("nombre",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tenant", "proveedor_cloud_primario")
    list_filter = ("proveedor_cloud_primario", "tenant")
    search_fields = ("nombre", "tenant__nombre")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("usuario", "tenant", "rol")
    list_filter = ("rol", "tenant")
    search_fields = ("usuario__email", "usuario__nombre", "tenant__nombre")
