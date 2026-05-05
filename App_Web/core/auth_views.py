import json
from urllib.parse import quote_plus, urlencode

from authlib.integrations.django_client import OAuth
from django.conf import settings
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.shortcuts import redirect, render
from django.urls import reverse
from core.models import Usuario

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
    return oauth.auth0.authorize_redirect(
        request, 
        request.build_absolute_uri(reverse("callback")),
        prompt="login"  # <--- Esto obliga a Auth0 a pedir usuario/contraseña siempre
    )

def callback(request):
    token = oauth.auth0.authorize_access_token(request)
    userinfo = token.get("userinfo")
    
    # Extraer el email y el rol del app_metadata (vía claims personalizados)
    email = userinfo.get("email")
    
    # Mapeo oficial para la entrega de BITE.co
    ROLE_MAPPING = {
        "administrador global": "ejecutivo_empresa",
        "gestor de proyecto": "responsable_proyecto",
        "analista de costos": "colaborador_limitado",
    }
    
    role_from_auth0 = (userinfo.get("https://bite-co/role") or userinfo.get("role") or "colaborador").lower()
    django_role = ROLE_MAPPING.get(role_from_auth0, "colaborador_limitado")
    
    if email:
        user, created = Usuario.objects.get_or_create(
            email=email,
            defaults={
                "nombre": userinfo.get("name", email),
                "rol_cliente": django_role,
            }
        )
        
        # Si el rol cambió en Auth0, lo actualizamos en la DB local
        if not created and user.rol_cliente != django_role:
            user.rol_cliente = django_role
            user.save()

        django_login(request, user)
        request.session["user"] = userinfo
        
    return redirect(reverse("api-index"))

def logout(request):
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
