from urllib.parse import urlencode

from django.conf import settings
from django.core import signing

SALT = "hereford.accion-correo.v1"


def firmar_accion(accion):
    return signing.Signer(salt=SALT).sign(str(accion.pk))


def construir_enlace(accion):
    parametros = {"token": firmar_accion(accion), "accion": accion.tipo}
    if accion.procesoid_id:
        parametros["codigo"] = accion.procesoid.codigo
    return settings.ACCESOS_URL_PUBLICA.rstrip("/") + "/acceso#" + urlencode(parametros)
