from accesos import views as accesos_views
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from cuestionario import views as cuestionario_views

router = DefaultRouter()
router.register(
    "postulantes", cuestionario_views.PostulanteViewSet, basename="postulante"
)
router.register(
    "areas", cuestionario_views.AreaVocacionalViewSet, basename="areavocacional"
)
router.register("preguntas", cuestionario_views.PreguntaViewSet, basename="pregunta")
router.register(
    "evaluaciones", cuestionario_views.EvaluacionViewSet, basename="evaluacion"
)
router.register(
    "mis-evaluaciones",
    accesos_views.MisEvaluacionesViewSet,
    basename="mis-evaluaciones",
)
router.register(
    "admin/procesos", accesos_views.ProcesoAdminViewSet, basename="admin-procesos"
)
router.register(
    "admin/invitaciones",
    accesos_views.InvitacionAdminViewSet,
    basename="admin-invitaciones",
)
router.register(
    "admin/asignaciones",
    accesos_views.AsignacionAdminViewSet,
    basename="admin-asignaciones",
)
router.register(
    "admin/gestores", accesos_views.GestorAdminViewSet, basename="admin-gestores"
)
router.register(
    "admin/participantes",
    accesos_views.ParticipanteAdminViewSet,
    basename="admin-participantes",
)

urlpatterns = [
    path("", include("accesos.urls")),
    path("", include(router.urls)),
]
