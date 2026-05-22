from rest_framework import serializers
from .models import Tenant, Project, UserProfile, Usuario


class TenantSerializer(serializers.ModelSerializer):
    """
    Serializador para el modelo Tenant.
    """
    class Meta:
        model = Tenant
        fields = ["id", "nombre", "estado", "plan", "creado_en"]
        read_only_fields = ["id", "creado_en"]


class ProjectSerializer(serializers.ModelSerializer):
    """
    Serializador para el modelo Project.
    Garantiza aislamiento multitenant validando la frontera lógica del Tenant.
    """
    class Meta:
        model = Project
        fields = ["id", "tenant", "nombre", "descripcion", "proveedor_cloud_primario"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None

        # Si el usuario está autenticado y no es superusuario, validar que pertenezca al mismo Tenant
        if user and user.is_authenticated and not user.is_superuser:
            user_profile = getattr(user, 'profile', None)
            if not user_profile:
                raise serializers.ValidationError("El usuario no tiene un perfil organizativo asociado.")
            
            tenant = attrs.get("tenant")
            if tenant != user_profile.tenant:
                raise serializers.ValidationError(
                    {"tenant": "No tienes autorización para crear o asociar proyectos en este Tenant."}
                )

        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializador para la relación entre el Usuario de Auth0 y su Tenant.
    """
    usuario_email = serializers.EmailField(source="usuario.email", read_only=True)
    usuario_nombre = serializers.CharField(source="usuario.nombre", read_only=True)

    class Meta:
        model = UserProfile
        fields = ["id", "usuario", "usuario_email", "usuario_nombre", "tenant", "rol"]
        read_only_fields = ["id"]
