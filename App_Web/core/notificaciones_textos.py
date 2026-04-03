"""Textos de notificación alineados con respuestas del cliente (cola / sobrecarga)."""


def asunto_reporte_sistema_sobrecargado() -> str:
    return "BITE.co — Su solicitud de reporte no pudo procesarse ahora"


def cuerpo_reporte_sistema_sobrecargado(nombre_usuario: str) -> str:
    return (
        f"Hola {nombre_usuario},\n\n"
        "En este momento el sistema está atendiendo un volumen alto de solicitudes "
        "y no pudimos generar su reporte de inmediato.\n\n"
        "No es necesario volver a enviar la solicitud de inmediato: puede consultar el "
        "historial de reportes más tarde o intentar de nuevo en unos minutos. "
        "Si el problema persiste, contacte a soporte.\n\n"
        "Gracias por su paciencia,\n"
        "Equipo BITE.co"
    )
