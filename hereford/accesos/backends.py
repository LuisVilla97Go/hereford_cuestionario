from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .models import IdentidadAcceso


class CorreoBackend(ModelBackend):
    def authenticate(self, request, correo=None, password=None, **kwargs):
        usuario = kwargs.get("username") or ""
        if correo is None and "@" in usuario:
            correo = usuario
        if correo is None or password is None:
            return None
        identidad = (
            IdentidadAcceso.objects.habilitadas()
            .select_related("usuarioid")
            .filter(correo=correo.strip().lower())
            .first()
        )
        if identidad is None:
            get_user_model()().set_password(password)
            return None
        user = identidad.usuarioid
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
