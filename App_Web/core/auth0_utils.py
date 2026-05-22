import json
import logging
from urllib.request import urlopen
import jwt
from django.conf import settings
from rest_framework import authentication, exceptions
from core.models import Usuario, Tenant, UserProfile, RolUserProfile

logger = logging.getLogger(__name__)


class Auth0JSONWebTokenAuthentication(authentication.BaseAuthentication):
    """
    Autenticación personalizada para validar tokens JWT emitidos por Auth0.
    Garantiza confidencialidad y validación de firma criptográfica local.
    """

    def authenticate(self, request):
        auth = authentication.get_authorization_header(request).split()

        if not auth or auth[0].lower() != b'bearer':
            return None

        if len(auth) == 1:
            raise exceptions.AuthenticationFailed("Encabezado de autorización inválido.")
        elif len(auth) > 2:
            raise exceptions.AuthenticationFailed("Encabezado de autorización debe ser Token Bearer.")

        token = auth[1].decode('utf-8')
        
        # 1. Obtener claves públicas de Auth0 (JWKS)
        try:
            jsonurl = urlopen(f"https://{settings.AUTH0_DOMAIN}/.well-known/jwks.json")
            jwks = json.loads(jsonurl.read())
        except Exception as e:
            logger.error(f"Error obteniendo JWKS desde Auth0: {str(e)}")
            raise exceptions.AuthenticationFailed(f"No se pudieron obtener claves de Auth0: {str(e)}")

        # 2. Decodificar el encabezado del token para encontrar la clave correcta (kid)
        try:
            unverified_header = jwt.get_unverified_header(token)
        except Exception:
            raise exceptions.AuthenticationFailed("Token mal formado.")

        rsa_key = {}
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"]
                }
        
        # 3. Validar la firma y el contenido del token
        if rsa_key:
            try:
                payload = jwt.decode(
                    token,
                    jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(rsa_key)),
                    algorithms=["RS256"],
                    audience=settings.AUTH0_API_AUDIENCE,
                    issuer=f"https://{settings.AUTH0_DOMAIN}/"
                )
            except jwt.ExpiredSignatureError:
                raise exceptions.AuthenticationFailed("El token ha expirado.")
            except jwt.JWTClaimsError:
                raise exceptions.AuthenticationFailed("Reclamos (claims) inválidos. Verifique audiencia y emisor.")
            except Exception as e:
                raise exceptions.AuthenticationFailed(f"Error validando token: {str(e)}")

            # 4. Obtener email del payload
            user_email = payload.get("email") or payload.get(f"{settings.AUTH0_API_AUDIENCE}/email")
            
            # Fallback para Machine-to-Machine (M2M) tokens o pruebas de carga
            if not user_email:
                user_email = f"m2m_{payload.get('sub')}"
            
            # 5. Obtener o crear el Usuario
            user, created = Usuario.objects.get_or_create(
                email=user_email,
                defaults={
                    "nombre": payload.get("name", user_email),
                }
            )

            # 6. Flujo estricto de asignación de Tenant y Perfil (Multitenancy)
            if not hasattr(user, 'profile'):
                tenant = None
                
                # Intentar buscar tenant_id en claims personalizados de Auth0
                tenant_id = payload.get("https://bite-co/tenant_id")
                if tenant_id:
                    tenant = Tenant.objects.filter(id=tenant_id).first()
                
                # Si no se encuentra asociado a ningún tenant (Sign-up Enterprise)
                if not tenant:
                    if "@" in user_email and not user_email.startswith("m2m_"):
                        domain = user_email.split("@")[1]
                        tenant_name = domain.split(".")[0].capitalize()
                    else:
                        tenant_name = "Enterprise Tenant"
                    
                    # Se crea un nuevo Tenant utilizando el dominio del correo
                    tenant = Tenant.objects.create(
                        nombre=tenant_name,
                        estado="activo",
                        plan="enterprise"
                    )
                    logger.info(f"Creado nuevo Tenant Enterprise '{tenant_name}' para el registro de {user_email}")

                # Determinar Rol (Admin / Viewer) basado en claims o permisos
                permissions = payload.get("permissions", [])
                scope = payload.get("scope", "").split()
                all_permissions = permissions + scope
                
                auth0_role = payload.get("https://bite-co/role") or payload.get("role") or ""
                if "admin" in auth0_role.lower() or "global" in auth0_role.lower():
                    django_role = RolUserProfile.ADMIN
                else:
                    django_role = RolUserProfile.VIEWER

                # Asociar perfil
                UserProfile.objects.create(
                    usuario=user,
                    tenant=tenant,
                    rol=django_role
                )
                logger.info(f"Asociado UserProfile con rol {django_role} y Tenant {tenant.nombre} al usuario {user_email}")
            
            # Adjuntamos permisos/claims al objeto usuario para autorización en memoria
            user.auth0_permissions = payload.get("permissions", []) + payload.get("scope", "").split()
            return (user, token)

        raise exceptions.AuthenticationFailed("No se pudo encontrar la clave pública adecuada.")
