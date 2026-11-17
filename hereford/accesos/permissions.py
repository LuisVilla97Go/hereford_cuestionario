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


class EsSuperusuario(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_superuser)


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


def organizacion_cliente(user):
    if not user or not user.is_authenticated or not user.is_active or user.is_staff:
        return None
    if not user.groups.filter(name="clientes").exists():
        return None
    identidad = (
        IdentidadAcceso.objects.habilitadas()
        .select_related("organizacionid")
        .filter(usuarioid=user, organizacionid__activa=True)
        .first()
    )
    return identidad.organizacionid if identidad else None


class EsCliente(BasePermission):
    def has_permission(self, request, view):
        return organizacion_cliente(request.user) is not None
