from rest_framework.permissions import BasePermission

from .models import IdentidadAcceso


class GestionaAccesos(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.is_staff
            and user.has_perm("accesos.gestionar_accesos")
        )


class EsParticipante(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        return (
            user.groups.filter(name="users").exists()
            and IdentidadAcceso.objects.habilitadas()
            .filter(usuarioid=user, postulanteid__isnull=False)
            .exists()
        )
