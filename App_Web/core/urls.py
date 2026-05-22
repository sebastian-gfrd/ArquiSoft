from django.urls import path
from .views import health, index
from .api_views import (
    TenantListCreateView,
    TenantRetrieveUpdateDestroyView,
    ProjectListCreateView,
    ProjectRetrieveUpdateDestroyView,
)
from . import auth_views

urlpatterns = [
    # Vistas de autenticación e información general
    path("", index, name="api-index"),
    path("health/", health, name="health"),
    path("login/", auth_views.login, name="login"),
    path("callback/", auth_views.callback, name="callback"),
    path("logout/", auth_views.logout, name="logout"),
    
    # Endpoints administrativos REST del Core (Multitenancy puro)
    path("api/v1/tenants/", TenantListCreateView.as_view(), name="tenant-list-create"),
    path("api/v1/tenants/<int:pk>/", TenantRetrieveUpdateDestroyView.as_view(), name="tenant-detail"),
    path("api/v1/projects/", ProjectListCreateView.as_view(), name="project-list-create"),
    path("api/v1/projects/<int:pk>/", ProjectRetrieveUpdateDestroyView.as_view(), name="project-detail"),
]
