import logging
from urllib.parse import quote_plus, urlencode
from authlib.integrations.django_client import OAuth
from django.conf import settings
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.shortcuts import redirect
from django.urls import reverse
from core.models import Usuario, Tenant, UserProfile, RolUserProfile

logger = logging.getLogger(__name__)

oauth = OAuth()

oauth.register(
    "auth0",
    client_id=settings.AUTH0_CLIENT_ID,
    client_secret=settings.AUTH0_CLIENT_SECRET,
    client_kwargs={
        "scope": "openid profile email",
    },
    server_metadata_url=f"https://{settings.AUTH0_DOMAIN}/.well-known/openid-configuration",
)


def login(request):
    """
    Redirecciona a Auth0 para iniciar el flujo de autenticación interactivo.
    """
    return oauth.auth0.authorize_redirect(
        request, 
        request.build_absolute_uri(reverse("callback")),
        prompt="login"  # Obliga a Auth0 a solicitar siempre credenciales
    )


def callback(request):
    """
    Callback de Auth0 tras la autenticación interactiva exitosa.
    Establece la sesión del usuario en Django asociando Tenant y UserProfile.
    """
    token = oauth.auth0.authorize_access_token(request)
    userinfo = token.get("userinfo")
    email = userinfo.get("email")
    
    if email:
        # 1. Obtener o crear Usuario básico
        user, created = Usuario.objects.get_or_create(
            email=email,
            defaults={
                "nombre": userinfo.get("name", email),
            },
        )
        
        # 2. Determinar Rol (Admin / Viewer) basado en claims de Auth0
        role_from_auth0 = (userinfo.get("https://bite-co/role") or userinfo.get("role") or "colaborador").lower()
        if "admin" in role_from_auth0 or "gestor" in role_from_auth0 or "global" in role_from_auth0:
            django_role = RolUserProfile.ADMIN
        else:
            django_role = RolUserProfile.VIEWER
            
        # 3. Flujo estricto de Tenant y Perfil (Multitenancy)
        profile = getattr(user, 'profile', None)
        if not profile:
            tenant = None
            
            # Buscar si el claim trae un tenant corporativo asociado
            tenant_id = userinfo.get("https://bite-co/tenant_id")
            if tenant_id:
                tenant = Tenant.objects.filter(id=tenant_id).first()
                
            # Si no hay tenant y es registro nuevo, crearlo en base a su dominio corporativo
            if not tenant:
                if "@" in email:
                    domain = email.split("@")[1]
                    tenant_name = domain.split(".")[0].capitalize()
                else:
                    tenant_name = "Enterprise Tenant"
                    
                tenant = Tenant.objects.create(
                    nombre=tenant_name,
                    estado="activo",
                    plan="enterprise"
                )
                logger.info(f"Creado nuevo Tenant Enterprise '{tenant_name}' en callback para {email}")
                
            profile = UserProfile.objects.create(
                usuario=user,
                tenant=tenant,
                rol=django_role
            )
        else:
            # Si el usuario ya tenía perfil, actualizar el rol o tenant si cambiaron en Auth0
            modified = False
            if profile.rol != django_role:
                profile.rol = django_role
                modified = True
                
            tenant_id = userinfo.get("https://bite-co/tenant_id")
            if tenant_id and profile.tenant.id != int(tenant_id):
                new_tenant = Tenant.objects.filter(id=tenant_id).first()
                if new_tenant:
                    profile.tenant = new_tenant
                    modified = True
                    
            if modified:
                profile.save()
                logger.info(f"Perfil de {email} actualizado con rol {django_role} y Tenant {profile.tenant.nombre}")

        # 4. Iniciar sesión en Django (las sesiones persistirán en Redis o DB fallback de desarrollo)
        django_login(request, user)
        request.session["user"] = userinfo
        
    return redirect(reverse("api-index"))


def logout(request):
    """
    Cierra la sesión local en Django y redirige al cierre de sesión global de Auth0.
    """
    django_logout(request)
    domain = settings.AUTH0_DOMAIN
    client_id = settings.AUTH0_CLIENT_ID
    return redirect(
        f"https://{domain}/v2/logout?"
        + urlencode(
            {
                "returnTo": request.build_absolute_uri(reverse("api-index")),
                "client_id": client_id,
            },
            quote_via=quote_plus,
        )
    )
