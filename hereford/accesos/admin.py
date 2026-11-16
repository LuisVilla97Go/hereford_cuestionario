from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from cuestionario.admin import SoloLectura

from . import services
from .forms import ProcesoAdminForm
from .models import (
    AccionCorreo,
    AsignacionEvaluacion,
    FotoParticipante,
    IdentidadAcceso,
    Invitacion,
    ProcesoEvaluacion,
)


class GestionAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.has_perm("accesos.gestionar_accesos")

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProcesoEvaluacion)
class ProcesoAdmin(GestionAdmin):
    form = ProcesoAdminForm
    list_display = ["titulo", "codigo", "modalidad", "activo", "inicio", "fin"]
    list_filter = ["activo", "modalidad"]
    search_fields = ["titulo", "codigo"]
    readonly_fields = ["id", "codigo", "creado_por"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(IdentidadAcceso)
class IdentidadAdmin(SoloLectura):
    list_display = ["id", "correo", "correo_verificado", "activacion_manual", "postulanteid"]
    list_select_related = ["postulanteid"]
    list_filter = ["correo_verificado"]
    search_fields = ["correo"]
    exclude = ["aviso_aceptado_en"]


@admin.register(Invitacion)
class InvitacionAdmin(SoloLectura):
    list_display = ["id", "procesoid", "correo", "vence_en", "revocada", "aceptada_en"]
    list_filter = ["revocada"]
    list_select_related = ["procesoid"]
    search_fields = ["correo", "procesoid__titulo"]
    actions = ["revocar", "reenviar"]

    def has_gestionar_permission(self, request):
        return request.user.has_perm("accesos.gestionar_accesos")

    @admin.action(description="Revocar invitaciones pendientes", permissions=["gestionar"])
    def revocar(self, request, queryset):
        for invitacion in queryset:
            try:
                services.revocar_invitacion(invitacion, request.user)
            except APIException:
                self.message_user(
                    request,
                    "Una invitación no se pudo revocar; compruebe su estado.",
                    level="ERROR",
                )

    @admin.action(description="Reencolar invitaciones pendientes", permissions=["gestionar"])
    def reenviar(self, request, queryset):
        for invitacion in queryset.select_related("procesoid"):
            try:
                services.invitar(request.user, invitacion.procesoid, invitacion.correo)
            except APIException:
                self.message_user(
                    request,
                    "Una invitación no se pudo reencolar; compruebe su estado.",
                    level="ERROR",
                )


@admin.register(AsignacionEvaluacion)
class AsignacionAdmin(SoloLectura):
    list_display = ["id", "procesoid", "identidadid", "activa", "creada_en"]
    list_filter = ["activa", "procesoid"]
    list_select_related = ["procesoid", "identidadid"]
    actions = ["revocar"]

    def has_gestionar_permission(self, request):
        return request.user.has_perm("accesos.gestionar_accesos")

    @admin.action(description="Revocar acceso a las asignaciones", permissions=["gestionar"])
    def revocar(self, request, queryset):
        for asignacion in queryset:
            services.revocar_asignacion(asignacion, request.user)


@admin.register(AccionCorreo)
class CorreoAdmin(SoloLectura):
    list_display = ["id", "tipo", "entrega_manual", "vence_en", "enviada_en", "usada_en"]
    list_filter = ["tipo"]
    exclude = ["credencial_version"]


@admin.register(FotoParticipante)
class FotoAdmin(SoloLectura):
    list_display = ["id", "identidadid", "tamano", "aceptada_en"]
    list_select_related = ["identidadid"]


class UsuarioAdmin(UserAdmin):
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj and IdentidadAcceso.objects.filter(usuarioid=obj).exists():
            return [*fields, "email", "username"]
        return fields


admin.site.unregister(get_user_model())
admin.site.register(get_user_model(), UsuarioAdmin)


class TokenAdmin(SoloLectura):
    exclude = ["token"]
    list_display = ["jti", "user", "expires_at"]
    list_select_related = ["user"]


admin.site.unregister(OutstandingToken)
admin.site.register(OutstandingToken, TokenAdmin)
admin.site.unregister(BlacklistedToken)
admin.site.register(BlacklistedToken, SoloLectura)
