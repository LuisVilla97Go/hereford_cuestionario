from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import generics, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from cuestionario.catalogo_cache import preguntas_participante
from cuestionario.exceptions import Conflicto
from cuestionario.models import RegistroCalificacion
from cuestionario.serializers import EnviarRespuestasSerializer

from . import fotos, services
from .models import AsignacionEvaluacion, IdentidadAcceso, Invitacion, ProcesoEvaluacion
from .permissions import EsParticipante, GestionaAccesos
from .serializers import (
    AceptarSerializer,
    ActivacionSerializer,
    AsignacionSerializer,
    FotoEntradaSerializer,
    InvitacionSalidaSerializer,
    InvitacionSerializer,
    LoginSerializer,
    ParticiparSerializer,
    ProcesoAdminSerializer,
    ProcesoPublicoSerializer,
    RecuperarSerializer,
    RefreshSerializer,
    RegistroSerializer,
    RestablecerSerializer,
    TokenSerializer,
)
from .throttles import LimitePersistente
from .uploads import LimiteFotoUploadHandler


class Publica(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LimitePersistente]

    def get_authenticate_header(self, request):
        return 'Bearer realm="api"'

    def entrada(self, cls):
        serializer = cls(data=self.request.data, context={"request": self.request})
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class LoginView(Publica):
    def post(self, request):
        return Response(services.iniciar_sesion(request=request, **self.entrada(LoginSerializer)))


class AccesoView(Publica):
    renderer_classes = [JSONRenderer]
    parser_classes = [JSONParser]

    @staticmethod
    def operaciones():
        return {
            "consultar_invitacion": {"metodo": "POST", "ruta": reverse("acceso-api")},
            "activar_cuenta": {"metodo": "POST", "ruta": reverse("invitacion-activar")},
            "iniciar_sesion": {"metodo": "POST", "ruta": reverse("correo-login")},
            "aceptar_con_cuenta_existente": {
                "metodo": "POST",
                "ruta": reverse("invitacion-aceptar"),
                "requiere_jwt": True,
            },
        }

    def get(self, request):
        return Response(
            {"tipo": "api", "campo_consulta": "token", "operaciones": self.operaciones()}
        )

    def post(self, request):
        proceso, vence_en = services.consultar_invitacion(self.entrada(TokenSerializer)["token"])
        return Response(
            {
                "estado": "vigente",
                "proceso": ProcesoPublicoSerializer(proceso).data,
                "vence_en": vence_en,
                "operaciones": self.operaciones(),
            }
        )


class RegistroView(Publica):
    def post(self, request):
        return Response(services.registrar(self.entrada(RegistroSerializer)), status=202)


class VerificarView(Publica):
    def post(self, request):
        services.verificar_correo(self.entrada(TokenSerializer)["token"])
        return Response({"detalle": "Correo verificado. Inicie sesión para continuar."})


class ActivarView(Publica):
    def post(self, request):
        return Response(services.activar_invitacion(self.entrada(ActivacionSerializer)), status=202)


class RecuperarView(Publica):
    def post(self, request):
        data = self.entrada(RecuperarSerializer)
        return Response(services.solicitar_correo(data["correo"], data.get("codigo")), status=202)


class RestablecerView(Publica):
    def post(self, request):
        data = self.entrada(RestablecerSerializer)
        services.restablecer(data["token"], data["password"])
        return Response({"detalle": "Contraseña actualizada. Inicie sesión."})


class RefreshView(Publica):
    def post(self, request):
        return Response(services.renovar(self.entrada(RefreshSerializer)["refresh"]))


class Privada(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]


class LogoutView(Privada):
    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cerrar_sesion(request.user, serializer.validated_data["refresh"])
        return Response(status=204)


class MeView(Privada):
    def get(self, request):
        identidad = get_object_or_404(IdentidadAcceso, usuarioid=request.user)
        return Response(
            {
                "correo": identidad.correo,
                "correo_verificado": identidad.correo_verificado,
                "activacion_manual": identidad.activacion_manual,
                "participante": bool(identidad.postulanteid_id),
                "puede_gestionar_accesos": GestionaAccesos().has_permission(request, self),
            }
        )


class FotoView(Privada):
    permission_classes = [EsParticipante]
    parser_classes = [MultiPartParser]

    def initialize_request(self, request, *args, **kwargs):
        request.upload_handlers.insert(0, LimiteFotoUploadHandler(request))
        return super().initialize_request(request, *args, **kwargs)

    def get(self, request):
        return Response(fotos.datos_foto(fotos.foto_propia(request.user)))

    def post(self, request):
        serializer = FotoEntradaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        foto = fotos.guardar_foto(request.user, serializer.validated_data["foto"])

        return Response(
            {"foto_registrada": True, "ancho": foto.ancho, "alto": foto.alto}, status=201
        )

    def delete(self, request):
        fotos.eliminar_foto(request.user)
        return Response(status=204)


class AceptarView(Privada):
    permission_classes = [EsParticipante]
    throttle_classes = [LimitePersistente]

    def post(self, request):
        serializer = AceptarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asignacion = services.aceptar_invitacion(
            request.user,
            serializer.validated_data["token"],
            serializer.validated_data["aviso_version"],
        )
        return Response(AsignacionSerializer(asignacion).data)


class ProcesoView(generics.RetrieveAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LimitePersistente]
    queryset = ProcesoEvaluacion.objects.all()
    serializer_class = ProcesoPublicoSerializer
    lookup_field = "codigo"


class ParticiparView(Privada):
    permission_classes = [EsParticipante]
    throttle_classes = [LimitePersistente]

    def post(self, request, codigo):
        serializer = ParticiparSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asignacion = services.participar(
            request.user, codigo, serializer.validated_data["aviso_version"]
        )
        return Response(AsignacionSerializer(asignacion).data)


class MisEvaluacionesViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [EsParticipante]
    serializer_class = AsignacionSerializer

    def get_queryset(self):
        return AsignacionEvaluacion.objects.filter(
            identidadid__usuarioid=self.request.user
        ).select_related("procesoid", "evaluacionid")

    @action(detail=True, methods=["get"])
    def preguntas(self, request, pk=None, format=None):
        asignacion = self.get_object()
        services.proceso_vigente(asignacion.procesoid)
        if not asignacion.activa:
            raise Conflicto("La asignación está revocada.")
        return Response(
            {
                "escala": [
                    {"valor": 1, "etiqueta": "Me desagrada mucho"},
                    {"valor": 2, "etiqueta": "No me gusta"},
                    {"valor": 3, "etiqueta": "Me es indiferente"},
                    {"valor": 4, "etiqueta": "Me gusta"},
                    {"valor": 5, "etiqueta": "Me gusta mucho"},
                ],
                "preguntas": preguntas_participante(),
            }
        )

    @action(detail=True, methods=["post"])
    def respuestas(self, request, pk=None, format=None):
        asignacion = self.get_object()
        serializer = EnviarRespuestasSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.enviar_respuestas(
            request.user, asignacion.pk, serializer.validated_data["respuestas"]
        )
        asignacion.evaluacionid.refresh_from_db()
        return Response(self.get_serializer(asignacion).data, status=201)

    @action(detail=True, methods=["get"])
    def estado(self, request, pk=None, format=None):
        asignacion = self.get_object()
        try:
            snapshot = asignacion.evaluacionid.registro_calificacion.snapshot
        except RegistroCalificacion.DoesNotExist:
            snapshot = {}
        return Response(
            {
                "completado": asignacion.evaluacionid.completado,
                "conversion_pendiente": bool(snapshot.get("areas_pendientes")),
                "devolucion_habilitada": False,
                "detalle": "La devolución requiere revisión y habilitación profesional.",
            }
        )


class ProcesoAdminViewSet(viewsets.ModelViewSet):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [GestionaAccesos]
    queryset = ProcesoEvaluacion.objects.all()
    serializer_class = ProcesoAdminSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        from django.db import transaction

        with transaction.atomic():
            obj = serializer.save(creado_por=self.request.user)
            services.auditar(self.request.user, obj, "Proceso creado.")

    def perform_update(self, serializer):
        from django.db import transaction

        with transaction.atomic():
            actual = ProcesoEvaluacion.objects.select_for_update().get(pk=serializer.instance.pk)
            vigente = type(serializer)(
                instance=actual,
                data=serializer.initial_data,
                partial=serializer.partial,
                context=serializer.context,
            )
            vigente.is_valid(raise_exception=True)
            obj = vigente.save()
            serializer.instance = obj
            services.auditar(self.request.user, obj, "Configuración del proceso modificada.")


class InvitacionAdminViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [GestionaAccesos]
    queryset = Invitacion.objects.select_related("procesoid").order_by("-vence_en", "id")
    serializer_class = InvitacionSalidaSerializer

    @action(detail=False, methods=["post"])
    def enlace(self, request, format=None):
        serializer = InvitacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            services.emitir_enlace_manual(
                request.user,
                serializer.validated_data["procesoid"],
                serializer.validated_data["correo"],
            ),
            status=201,
        )

    def create(self, request, format=None):
        serializer = InvitacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitacion = services.invitar(
            request.user,
            serializer.validated_data["procesoid"],
            serializer.validated_data["correo"],
        )
        return Response(self.get_serializer(invitacion).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def revocar(self, request, pk=None, format=None):
        services.revocar_invitacion(self.get_object(), request.user)
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def reenviar(self, request, pk=None, format=None):
        anterior = self.get_object()
        nueva = services.invitar(request.user, anterior.procesoid, anterior.correo)
        return Response(self.get_serializer(nueva).data)


class AsignacionAdminViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [GestionaAccesos]
    queryset = AsignacionEvaluacion.objects.select_related("procesoid", "evaluacionid")
    serializer_class = AsignacionSerializer

    @action(detail=True, methods=["post"])
    def revocar(self, request, pk=None, format=None):
        services.revocar_asignacion(self.get_object(), request.user)
        return Response(status=204)
