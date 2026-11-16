from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from .enlaces import construir_enlace
from .models import AccionCorreo


@transaction.atomic
def despachar_uno():
    if not settings.ACCESOS_ENVIOS_HABILITADOS:
        raise ImproperlyConfigured("Los envíos están deshabilitados.")
    accion = (
        AccionCorreo.objects.select_for_update(skip_locked=True)
        .filter(
            enviada_en__isnull=True,
            usada_en__isnull=True,
            vence_en__gt=timezone.now(),
            entrega_manual=False,
        )
        .first()
    )
    if accion is None:
        return False
    enlace = construir_enlace(accion)
    mensaje = EmailMessage(
        subject="Acceso a orientación vocacional Hereford",
        body=f"Recibimos una solicitud de acceso ({accion.get_tipo_display()}).\n"
        f"Continúe en: {enlace}\n"
        "Si no solicitó este acceso, ignore este mensaje. No comparta el enlace.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[accion.correo],
    )
    if mensaje.send(using="default") != 1:
        raise RuntimeError("No se pudo entregar el correo; permanece pendiente.")
    accion.enviada_en = timezone.now()
    accion.save(update_fields=["enviada_en"])
    return True
