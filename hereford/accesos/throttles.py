import ipaddress
import time

from django.conf import settings
from django.db import transaction
from django.utils.crypto import salted_hmac
from rest_framework.throttling import BaseThrottle

from .models import LimiteAcceso


def ip_cliente(request):
    remota = request.META.get("REMOTE_ADDR", "")
    if not getattr(settings, "ACCESOS_PROXY_CONFIABLE", False):
        return remota
    if getattr(settings, "ACCESOS_PROXY_RENDER", False):
        reenviada = request.META.get("HTTP_CF_CONNECTING_IP", "")
    else:
        reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "").rsplit(",", 1)[-1]
    try:
        return str(ipaddress.ip_address(reenviada.strip()))
    except ValueError:
        return remota


class LimitePersistente(BaseThrottle):
    periodo = 600
    maximo = 300

    def _admitir(self, identificador, maximo, ventana):
        clave = salted_hmac("limite-acceso", identificador, algorithm="sha256").hexdigest()
        with transaction.atomic():
            LimiteAcceso.objects.get_or_create(clave=clave, defaults={"ventana": ventana})
            fila = LimiteAcceso.objects.select_for_update().get(pk=clave)
            if fila.ventana != ventana:
                fila.ventana, fila.intentos = ventana, 0
            if fila.intentos >= maximo:
                return False
            fila.intentos += 1
            fila.save(update_fields=["ventana", "intentos"])
        return True

    def allow_request(self, request, view):
        ventana = int(time.time()) // self.periodo
        alcance = type(view).__name__
        if not self._admitir("ip:" + ip_cliente(request) + alcance, self.maximo, ventana):
            return False
        correo = request.data.get("correo") if isinstance(request.data, dict) else None
        if isinstance(correo, str):
            return self._admitir("correo:" + correo.strip().lower() + alcance, 10, ventana)
        return True

    def wait(self):
        return self.periodo - int(time.time()) % self.periodo
