import json
from urllib.request import urlopen

import jwt
from django.conf import settings
from rest_framework import authentication, exceptions


class Auth0JSONWebTokenAuthentication(authentication.BaseAuthentication):
    """
    Autenticación personalizada para validar tokens JWT emitidos por Auth0.
    Cumple con ASR3 (Confidencialidad).
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

            # 4. Vincular con un usuario de la base de datos (o devolver usuario anónimo con el payload)
            # En una implementación real, buscaríamos el usuario por el sub del payload.
            from core.models import Usuario
            user_email = payload.get("email") or payload.get(f"{settings.AUTH0_API_AUDIENCE}/email")
            
            # 4. Validar Scopes/Permissions (RBAC para ASR3)
            # Buscamos permisos en el campo 'permissions' (estándar de Auth0) o 'scope'
            permissions = payload.get("permissions", [])
            scope = payload.get("scope", "").split()
            
            # 5. Vincular con un usuario de la base de datos
            from core.models import Usuario
            user_email = payload.get("email") or payload.get(f"{settings.AUTH0_API_AUDIENCE}/email")
            
            if user_email:
                user, created = Usuario.objects.get_or_create(
                    email=user_email,
                    defaults={
                        "nombre": payload.get("name", user_email),
                        "rol_cliente": "colaborador_limitado",
                    }
                )
                # Adjuntamos los permisos al objeto usuario para usarlos en la app
                user.auth0_permissions = permissions + scope
                return (user, token)
            
            # Fallback si no hay email en el token
            raise exceptions.AuthenticationFailed("El token de Auth0 no contiene un email válido.")

        raise exceptions.AuthenticationFailed("No se pudo encontrar la clave pública adecuada.")
