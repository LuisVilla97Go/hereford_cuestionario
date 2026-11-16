from rest_framework.permissions import DjangoModelPermissions


class PersonalConPermisos(DjangoModelPermissions):
    perms_map = {
        **DjangoModelPermissions.perms_map,
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
    }

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active and user.is_staff):
            return False
        if not super().has_permission(request, view):
            return False
        extra = getattr(view, "permisos_por_accion", {}).get(getattr(view, "action", None), [])
        return user.has_perms(extra)
