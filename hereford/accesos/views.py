from uuid import UUID

from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import generics, mixins, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
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
from .models import (
    AsignacionEvaluacion,
    IdentidadAcceso,
    Invitacion,
    Organizacion,
    Pago,
    ProcesoEvaluacion,
)
from .permissions import (
    EsCliente,
    EsParticipante,
    EsSuperusuario,
    GestionaAccesos,
    organizacion_cliente,
)
from .serializers import (
    AceptarSerializer,
    ActivacionSerializer,
    AnulacionSerializer,
    AsignacionSerializer,
    ClienteAltaSerializer,
    ClienteSerializer,
    FotoEntradaSerializer,
    GestorAltaSerializer,
    GestorEdicionSerializer,
    GestorSerializer,
    InvitacionSalidaSerializer,
    InvitacionSerializer,
    LoginSerializer,
    OrganizacionSerializer,
    PagoEntradaSerializer,
    PagoSerializer,
    ParticipanteEdicionSerializer,
    ParticipanteSerializer,
    ParticiparSerializer,
    ProcesoAdminSerializer,
    ProcesoClienteSerializer,
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
            "fijar_contrasena": {"metodo": "POST", "ruta": reverse("correo-restablecer")},
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
        return Response(services.registrar(self.entrada(RegistroSerializer)), status=201)


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
                "es_cliente": EsCliente().has_permission(request, self),
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

    def get_object(self):
        try:
            return super().get_object()
        except Http404 as exc:
            raise NotFound("No se encontró un proceso de evaluación con ese código.") from exc


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


class AlcanceInstitucion:
    campo_organizacion = "organizacionid"

    def alcance(self):
        if not hasattr(self, "_alcance"):
            if GestionaAccesos().has_permission(self.request, self):
                self._alcance = None
            else:
                organizacion = organizacion_cliente(self.request.user)
                if organizacion is None:
                    raise PermissionDenied()
                self._alcance = organizacion
        return self._alcance

    def get_queryset(self):
        consulta = super().get_queryset()
        organizacion = self.alcance()
        if organizacion is None:
            return consulta
        return consulta.filter(**{self.campo_organizacion: organizacion})

    def procesos_visibles(self):
        organizacion = self.alcance()
        consulta = ProcesoEvaluacion.objects.all()
        return consulta if organizacion is None else consulta.filter(organizacionid=organizacion)


class ProcesoAdminViewSet(AlcanceInstitucion, viewsets.ModelViewSet):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [GestionaAccesos | EsCliente]
    queryset = ProcesoEvaluacion.objects.all()
    serializer_class = ProcesoAdminSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.alcance() is not None:
            return ProcesoClienteSerializer
        return ProcesoAdminSerializer

    def perform_create(self, serializer):
        extra = {"creado_por": self.request.user}
        if self.alcance() is not None:
            extra["organizacionid"] = self.alcance()
        with transaction.atomic():
            obj = serializer.save(**extra)
            services.auditar(self.request.user, obj, "Proceso creado.")

    def perform_update(self, serializer):
        with transaction.atomic():
            actual = ProcesoEvaluacion.objects.select_for_update().get(pk=serializer.instance.pk)
            vigente = type(serializer)(
                instance=actual,
                data=serializer.initial_data,
                partial=serializer.partial,
                context=serializer.context,
            )
            vigente.is_valid(raise_exception=True)
            nueva = vigente.validated_data.get("organizacionid", actual.organizacionid)
            if (
                getattr(nueva, "pk", None) != actual.organizacionid_id
                and AsignacionEvaluacion.objects.filter(procesoid=actual).exists()
            ):
                raise Conflicto(
                    "El evento ya tiene asignaciones; no se puede cambiar su institución."
                )
            obj = vigente.save()
            serializer.instance = obj
            services.auditar(self.request.user, obj, "Configuración del proceso modificada.")

    def perform_destroy(self, instance):
        services.eliminar_proceso(self.request.user, instance)


class InvitacionAdminViewSet(AlcanceInstitucion, viewsets.ReadOnlyModelViewSet):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [GestionaAccesos | EsCliente]
    queryset = Invitacion.objects.select_related("procesoid").order_by("-vence_en", "id")
    serializer_class = InvitacionSalidaSerializer
    campo_organizacion = "procesoid__organizacionid"

    def entrada(self, request):
        serializer = InvitacionSerializer(data=request.data)
        serializer.fields["procesoid"].queryset = self.procesos_visibles()
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @staticmethod
    def con_aviso(datos, proceso):
        aviso = services.aviso_cupos(proceso)
        return {**datos, "aviso_cupos": aviso} if aviso else datos

    @action(detail=False, methods=["post"])
    def enlace(self, request, format=None):
        datos = self.entrada(request)
        enlace = services.emitir_enlace_manual(request.user, datos["procesoid"], datos["correo"])
        return Response(self.con_aviso(enlace, datos["procesoid"]), status=201)

    def create(self, request, format=None):
        datos = self.entrada(request)
        invitacion = services.invitar(request.user, datos["procesoid"], datos["correo"])
        return Response(
            self.con_aviso(self.get_serializer(invitacion).data, invitacion.procesoid),
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def revocar(self, request, pk=None, format=None):
        services.revocar_invitacion(self.get_object(), request.user)
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def reenviar(self, request, pk=None, format=None):
        anterior = self.get_object()
        nueva = services.invitar(request.user, anterior.procesoid, anterior.correo)
        return Response(self.con_aviso(self.get_serializer(nueva).data, nueva.procesoid))


class CuentaAdminViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    edicion_serializer = None
    mensaje_edicion = ""

    def update(self, request, *args, **kwargs):
        entrada = self.edicion_serializer(data=request.data, partial=True)
        entrada.is_valid(raise_exception=True)
        objetivo = self.get_object()
        with transaction.atomic():
            identidad = IdentidadAcceso.objects.select_for_update().get(pk=objetivo.pk)
            self.guardar_edicion(identidad, entrada.validated_data)
            services.auditar(request.user, identidad, self.mensaje_edicion)
        return Response(self.get_serializer(self.get_queryset().get(pk=identidad.pk)).data)

    @action(detail=True, methods=["post"])
    def desactivar(self, request, pk=None, format=None):
        services.desactivar_identidad(self.get_object(), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def reactivar(self, request, pk=None, format=None):
        services.reactivar_identidad(self.get_object(), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def destroy(self, request, *args, **kwargs):
        services.eliminar_identidad(self.get_object(), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class GestorAdminViewSet(CuentaAdminViewSet):
    permission_classes = [EsSuperusuario]
    serializer_class = GestorSerializer
    edicion_serializer = GestorEdicionSerializer
    mensaje_edicion = "Datos del gestor modificados."
    queryset = (
        IdentidadAcceso.objects.filter(usuarioid__is_staff=True, usuarioid__is_superuser=False)
        .select_related("usuarioid")
        .order_by("correo")
    )

    def guardar_edicion(self, identidad, datos):
        if "correo" in datos:
            services.cambiar_correo(identidad, datos.pop("correo"))
        usuario = identidad.usuarioid
        for campo, valor in datos.items():
            setattr(usuario, campo, valor)
        if datos:
            usuario.save(update_fields=list(datos))

    def create(self, request, format=None):
        entrada = GestorAltaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        with transaction.atomic():
            identidad = services.crear_gestor(**entrada.validated_data)
            services.auditar(request.user, identidad, "Gestor creado.")
            enlace = services.emitir_enlace_gestor(request.user, identidad)
        datos = {**self.get_serializer(identidad).data, **enlace}
        return Response(datos, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def enlace(self, request, pk=None, format=None):
        return Response(
            services.emitir_enlace_gestor(request.user, self.get_object()),
            status=status.HTTP_201_CREATED,
        )


class ParticipanteAdminViewSet(AlcanceInstitucion, CuentaAdminViewSet):
    permission_classes = [GestionaAccesos]
    serializer_class = ParticipanteSerializer
    edicion_serializer = ParticipanteEdicionSerializer
    mensaje_edicion = "Datos del participante modificados."
    ESTADOS = {
        "desactivada": Q(desactivada_en__isnull=False),
        "habilitada": Q(desactivada_en__isnull=True)
        & (Q(correo_verificado=True) | Q(activacion_manual=True)),
        "pendiente": Q(
            desactivada_en__isnull=True, correo_verificado=False, activacion_manual=False
        ),
    }

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [(GestionaAccesos | EsCliente)()]
        return super().get_permissions()

    def get_queryset(self):
        organizacion = self.alcance()
        consulta = IdentidadAcceso.objects.filter(postulanteid__isnull=False)
        conteo = Count("asignacionevaluacion")
        if organizacion is not None:
            propias = AsignacionEvaluacion.objects.filter(
                identidadid=OuterRef("pk"), procesoid__organizacionid=organizacion
            )
            consulta = consulta.filter(Exists(propias))
            conteo = Count(
                "asignacionevaluacion",
                filter=Q(asignacionevaluacion__procesoid__organizacionid=organizacion),
            )
        consulta = (
            consulta.select_related("usuarioid", "postulanteid")
            .annotate(asignaciones=conteo)
            .order_by("correo")
        )
        estado = self.request.query_params.get("estado")
        if estado in self.ESTADOS:
            consulta = consulta.filter(self.ESTADOS[estado])
        if texto := self.request.query_params.get("q", "").strip():
            consulta = consulta.filter(
                Q(correo__icontains=texto) | Q(postulanteid__apellido_paterno__icontains=texto)
            )
        return consulta

    def guardar_edicion(self, identidad, datos):
        if "correo" in datos:
            services.cambiar_correo(identidad, datos.pop("correo"))
        if datos:
            services.corregir_ficha(identidad, datos)

    @action(detail=True, methods=["post"])
    def enlace(self, request, pk=None, format=None):
        return Response(
            services.emitir_enlace_participante(request.user, self.get_object()),
            status=status.HTTP_201_CREATED,
        )


class AsignacionAdminViewSet(AlcanceInstitucion, viewsets.ReadOnlyModelViewSet):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [GestionaAccesos | EsCliente]
    queryset = AsignacionEvaluacion.objects.select_related("procesoid", "evaluacionid")
    serializer_class = AsignacionSerializer
    campo_organizacion = "procesoid__organizacionid"

    @action(detail=True, methods=["post"])
    def revocar(self, request, pk=None, format=None):
        services.revocar_asignacion(self.get_object(), request.user)
        return Response(status=204)


def con_cupos(consulta):
    comprados = (
        Pago.objects.filter(organizacionid=OuterRef("pk"))
        .values("organizacionid")
        .annotate(total=Sum("cupos"))
        .values("total")
    )
    usados = (
        AsignacionEvaluacion.objects.filter(procesoid__organizacionid=OuterRef("pk"))
        .values("procesoid__organizacionid")
        .annotate(total=Count("id"))
        .values("total")
    )
    return consulta.annotate(
        cupos_comprados=Coalesce(Subquery(comprados), 0),
        cupos_usados=Coalesce(Subquery(usados), 0),
    )


def incluir_prueba(request):
    return request.query_params.get("incluir_prueba") == "1"


class OrganizacionAdminViewSet(viewsets.ModelViewSet):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [GestionaAccesos]
    serializer_class = OrganizacionSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        consulta = con_cupos(Organizacion.objects.all())
        if self.action == "list" and not incluir_prueba(self.request):
            consulta = consulta.filter(es_prueba=False)
        return consulta

    def guardar(self, serializer, mensaje):
        with transaction.atomic():
            obj = serializer.save()
            services.auditar(self.request.user, obj, mensaje)
        serializer.instance = con_cupos(Organizacion.objects.all()).get(pk=obj.pk)

    def perform_create(self, serializer):
        self.guardar(serializer, "Institución creada.")

    def perform_update(self, serializer):
        self.guardar(serializer, "Institución modificada.")

    def perform_destroy(self, instance):
        services.eliminar_organizacion(self.request.user, instance)


class PagoAdminViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [GestionaAccesos]
    serializer_class = PagoSerializer

    def get_queryset(self):
        consulta = Pago.objects.select_related("anulacion")
        if self.action == "list":
            if not incluir_prueba(self.request):
                consulta = consulta.filter(es_prueba=False)
            if organizacion := self.request.query_params.get("organizacion"):
                try:
                    consulta = consulta.filter(organizacionid=UUID(organizacion))
                except ValueError:
                    consulta = consulta.none()
        return consulta

    def create(self, request, format=None):
        entrada = PagoEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        pago, enlace = services.registrar_pago(request.user, dict(entrada.validated_data))
        datos = self.get_serializer(pago).data
        if enlace:
            datos = {**datos, "enlace": enlace["enlace"], "vence_en": enlace["vence_en"]}
        return Response(datos, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None, format=None):
        entrada = AnulacionSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        anulacion = services.anular_pago(request.user, self.get_object(), **entrada.validated_data)
        return Response(self.get_serializer(anulacion).data, status=status.HTTP_201_CREATED)


class ClienteAdminViewSet(GestorAdminViewSet):
    permission_classes = [GestionaAccesos]
    serializer_class = ClienteSerializer
    mensaje_edicion = "Datos del cliente modificados."
    queryset = (
        IdentidadAcceso.objects.filter(organizacionid__isnull=False)
        .select_related("usuarioid", "organizacionid")
        .order_by("correo")
    )

    def create(self, request, format=None):
        entrada = ClienteAltaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = dict(entrada.validated_data)
        with transaction.atomic():
            identidad = services.crear_cliente(organizacion=datos.pop("organizacionid"), **datos)
            services.auditar(request.user, identidad, "Cliente creado.")
            enlace = services.emitir_enlace_gestor(request.user, identidad)
        datos = {**self.get_serializer(identidad).data, **enlace}
        return Response(datos, status=status.HTTP_201_CREATED)


class CuposView(Privada):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [EsCliente]

    def get(self, request):
        organizacion = organizacion_cliente(request.user)
        return Response(
            {
                "organizacion": {"id": organizacion.pk, "nombre": organizacion.nombre},
                **services.cupos_de(organizacion),
                "invitaciones_pendientes": services.invitaciones_pendientes(organizacion),
            }
        )
