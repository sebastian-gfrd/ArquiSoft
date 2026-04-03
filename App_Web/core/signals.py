from datetime import timedelta

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver
from django.utils import timezone

from .http_utils import direccion_ip_cliente
from .models import Acceso, TipoEventoAcceso


@receiver(user_login_failed)
def registrar_intento_fallido(sender, credentials, request, **kwargs):
    if request is None:
        return
    email = credentials.get("email") or credentials.get("username") or ""
    Acceso.objects.create(
        usuario=None,
        fecha=timezone.now(),
        duracion=timedelta(0),
        tipo_evento=TipoEventoAcceso.LOGIN,
        exitoso=False,
        ip_address=direccion_ip_cliente(request) or None,
        ruta=getattr(request, "path", "") or "",
        detalle=f"Intento de inicio de sesión fallido: {email}",
    )


@receiver(user_logged_in)
def registrar_sesion_iniciada(sender, request, user, **kwargs):
    if request is None:
        return
    Acceso.objects.create(
        usuario=user,
        fecha=timezone.now(),
        duracion=timedelta(0),
        tipo_evento=TipoEventoAcceso.LOGIN,
        exitoso=True,
        ip_address=direccion_ip_cliente(request) or None,
        ruta=getattr(request, "path", "") or "",
        detalle="Inicio de sesión correcto",
    )
