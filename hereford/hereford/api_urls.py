from django.urls import include, path
from rest_framework.routers import DefaultRouter

from accesos import catalogo as accesos_catalogo
from accesos import views as accesos_views
from cuestionario import views as cuestionario_views

router = DefaultRouter()
router.register("postulantes", cuestionario_views.PostulanteViewSet, basename="postulante")
router.register("areas", cuestionario_views.AreaVocacionalViewSet, basename="areavocacional")
router.register("preguntas", cuestionario_views.PreguntaViewSet, basename="pregunta")
router.register("evaluaciones", cuestionario_views.EvaluacionViewSet, basename="evaluacion")
router.register(
    "mis-evaluaciones", accesos_views.MisEvaluacionesViewSet, basename="mis-evaluaciones"
)
router.register("admin/procesos", accesos_views.ProcesoAdminViewSet, basename="admin-procesos")
router.register(
    "admin/invitaciones", accesos_views.InvitacionAdminViewSet, basename="admin-invitaciones"
)
router.register(
    "admin/asignaciones", accesos_views.AsignacionAdminViewSet, basename="admin-asignaciones"
)
router.register("admin/gestores", accesos_views.GestorAdminViewSet, basename="admin-gestores")
router.register(
    "admin/participantes",
    accesos_views.ParticipanteAdminViewSet,
    basename="admin-participantes",
)
router.register(
    "admin/organizaciones",
    accesos_views.OrganizacionAdminViewSet,
    basename="admin-organizaciones",
)
router.register("admin/pagos", accesos_views.PagoAdminViewSet, basename="admin-pagos")
router.register("admin/clientes", accesos_views.ClienteAdminViewSet, basename="admin-clientes")
router.register(
    "admin/preguntas", accesos_catalogo.PreguntaAdminViewSet, basename="admin-preguntas"
)
router.register("admin/baremos", accesos_catalogo.BaremoAdminViewSet, basename="admin-baremos")

urlpatterns = [
    path("", include("accesos.urls")),
    path("", include(router.urls)),
]
