from django.contrib import admin
from django.urls import path, include
from . import views # Ajusta según tus vistas

urlpatterns = [
    # Envolvemos todo dentro del prefijo /auth/ para que coincida con el ALB
    path('auth/', include([
        path('admin/', admin.site.urls),
        path('health/', views.health, name='health'),
        path('login/', views.login, name='login'),
        path('callback/', views.callback, name='callback'),
        path('logout/', views.logout, name='logout'),
        
        # Tus APIs de tenants y proyectos
        path('api/v1/tenants/', views.TenantListCreate.as_view(), name='tenant-list-create'),
        path('api/v1/tenants/<int:pk>/', views.TenantDetail.as_view(), name='tenant-detail'),
        path('api/v1/projects/', views.ProjectListCreate.as_view(), name='project-list-create'),
        path('api/v1/projects/<int:pk>/', views.ProjectDetail.as_view(), name='project-detail'),
    ])),
]