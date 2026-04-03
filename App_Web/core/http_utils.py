from django.http import HttpRequest


def direccion_ip_cliente(request: HttpRequest) -> str | None:
    encabezado = request.META.get("HTTP_X_FORWARDED_FOR")
    if encabezado:
        return encabezado.split(",")[0].strip()
    addr = request.META.get("REMOTE_ADDR")
    return str(addr) if addr else None
