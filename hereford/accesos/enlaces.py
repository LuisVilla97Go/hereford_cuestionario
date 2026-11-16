from urllib.parse import urlencode

from django.conf import settings

from .services import firmar_accion


def construir_enlace(accion):
    parametros = {"token": firmar_accion(accion), "accion": accion.tipo}
    if accion.procesoid_id:
        parametros["codigo"] = accion.procesoid.codigo
    return settings.ACCESOS_URL_PUBLICA.rstrip("/") + "/acceso#" + urlencode(parametros)
