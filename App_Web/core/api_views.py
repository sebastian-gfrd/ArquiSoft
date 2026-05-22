from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Tenant, Project
from .serializers import TenantSerializer, ProjectSerializer, UserProfileSerializer
import logging

logger = logging.getLogger(__name__)


class TenantListCreateView(generics.ListCreateAPIView):
    """
    Vista para listar y crear Tenants.
    Implementa seguridad multitenant restringiendo los resultados al Tenant del usuario autenticado.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TenantSerializer

    def get_queryset(self):
        user = self.request.user
        
        # Superusuarios ven todos los Tenants en el sistema
        if user.is_superuser:
            return Tenant.objects.all()

        # Usuarios estándar solo ven su propio Tenant asociado
        user_profile = getattr(user, 'profile', None)
        if not user_profile:
            return Tenant.objects.none()
            
        return Tenant.objects.filter(id=user_profile.tenant.id)


class TenantRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    Vista para ver, actualizar o eliminar un Tenant específico.
    Garantiza el estricto aislamiento de datos.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TenantSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Tenant.objects.all()

        user_profile = getattr(user, 'profile', None)
        if not user_profile:
            return Tenant.objects.none()
            
        return Tenant.objects.filter(id=user_profile.tenant.id)


class ProjectListCreateView(generics.ListCreateAPIView):
    """
    Vista para listar y crear Proyectos.
    Implementa seguridad multitenant filtrando proyectos por el Tenant del usuario.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectSerializer

    def get_queryset(self):
        user = self.request.user
        
        # Superusuarios ven todos los proyectos del sistema
        if user.is_superuser:
            return Project.objects.all()

        # Usuarios estándar solo ven proyectos de su Tenant
        user_profile = getattr(user, 'profile', None)
        if not user_profile:
            return Project.objects.none()
            
        return Project.objects.filter(tenant=user_profile.tenant)

    def perform_create(self, serializer):
        user = self.request.user
        
        # Para usuarios estándar, forzar la asociación al Tenant de su propio perfil organizacional
        if not user.is_superuser:
            user_profile = getattr(user, 'profile', None)
            if user_profile:
                serializer.save(tenant=user_profile.tenant)
                return
        
        serializer.save()


class ProjectRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    Vista para ver, actualizar o eliminar un Proyecto específico de forma segura.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Project.objects.all()

        user_profile = getattr(user, 'profile', None)
        if not user_profile:
            return Project.objects.none()
            
        return Project.objects.filter(tenant=user_profile.tenant)
