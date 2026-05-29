from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Envolvemos todo dentro del prefijo /auth/ para que coincida con el ALB
    path('auth/', include([
        path('admin/', admin.site.urls),
        path('', include('core.urls')),
    ])),
]