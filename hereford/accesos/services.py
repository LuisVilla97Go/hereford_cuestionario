from datetime import timedelta
from uuid import UUID, uuid4
from django.contrib.admin.models import CHANGE, DELETION, LogEntry
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import signing
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import AuthenticationFailed, NotFound, ValidationError
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken
from cuestionario.exceptions import Conflicto
from cuestionario.models import Evaluacion, Postulante
from cuestionario.services import registrar_respuestas

from .models import (
    AccionCorreo,
    AsignacionEvaluacion,
    IdentidadAcceso,
    Invitacion,
    ProcesoEvaluacion,
)
from .serializers import comprobar_password

MENSAJE_CORREO = {"detalle": "Si corresponde, recibirá instrucciones en su correo."}
MENSAJE_ACTIVACION = {
    "detalle": "Solicitud procesada. Si corresponde, puede iniciar sesión."
}
SALT = "hereford.accion-correo.v1"


@sensitive_variables()
def iniciar_sesion(*, correo, password, request=None):
    user = authenticate(request=request, correo=correo, password=password)
    if user is None or not user.is_active:
        raise AuthenticationFailed("Credenciales inválidas.")
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _bloquear_correo(correo):
    from django.utils.crypto import salted_hmac

    clave = int(
        salted_hmac("identidad", correo, algorithm="sha256").hexdigest()[:15], 16
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [clave])


def auditar(user, obj, mensaje):
    LogEntry.objects.log_actions(
        user_id=user.pk, queryset=[obj], action_flag=CHANGE, change_message=mensaje
    )


def _esta_vigente(proceso):
    ahora = timezone.now()
    return proceso.activo and proceso.inicio <= ahora < proceso.fin


def proceso_vigente(proceso):
    if not _esta_vigente(proceso):
        raise Conflicto("El proceso no admite participación en este momento.")


def _proceso(codigo):
    try:
        proceso = ProcesoEvaluacion.objects.select_for_update().get(codigo=codigo)
    except ProcesoEvaluacion.DoesNotExist as exc:
        raise NotFound("Proceso inexistente.") from exc
    proceso_vigente(proceso)
    return proceso


def _encolar(
    tipo, correo, *, identidad=None, proceso=None, invitacion=None, manual=False
):
    ahora = timezone.now()
    pendientes = AccionCorreo.objects.filter(
        tipo=tipo, correo=correo, usada_en__isnull=True
    )
    if tipo != AccionCorreo.Tipo.VERIFICAR:
        pendientes = pendientes.filter(procesoid=proceso)
    pendientes.update(usada_en=ahora)
    return AccionCorreo.objects.create(
        tipo=tipo,
        correo=correo,
        identidadid=identidad,
        procesoid=proceso,
        invitacionid=invitacion,
        credencial_version=(
            identidad.usuarioid.get_session_auth_hash() if identidad else ""
        ),
        entrega_manual=manual,
        vence_en=(
            min(ahora + timedelta(hours=72), invitacion.vence_en)
            if invitacion
            else ahora + timedelta(hours=1)
        ),
    )


def firmar_accion(accion):
    return signing.Signer(salt=SALT).sign(str(accion.pk))


def _leer_accion(token, tipo):
    try:
        pk = UUID(signing.Signer(salt=SALT).unsign(token))
        accion = AccionCorreo.objects.get(pk=pk, tipo=tipo)
    except (signing.BadSignature, ValueError, AccionCorreo.DoesNotExist) as exc:
        raise ValidationError("Enlace inválido o vencido.") from exc
    return accion


def _accion_bloqueada(accion):
    accion = AccionCorreo.objects.select_for_update().get(pk=accion.pk)
    if accion.usada_en or accion.vence_en <= timezone.now():
        raise ValidationError("Enlace inválido o vencido.")
    if accion.identidadid_id:
        if (
            accion.credencial_version
            != accion.identidadid.usuarioid.get_session_auth_hash()
        ):
            raise ValidationError("Enlace inválido o vencido.")
    return accion


def _nueva_identidad(data):
    try:
        return _crear_identidad(data)
    except IntegrityError:
        if (
            IdentidadAcceso.objects.filter(correo=data["correo"]).exists()
            or Postulante.objects.filter(dni=data["datos"]["dni"]).exists()
        ):
            return None
        raise


@transaction.atomic
def _crear_identidad(data):
    correo = data["correo"]
    if (
        IdentidadAcceso.objects.filter(correo=correo).exists()
        or get_user_model().objects.filter(email__iexact=correo).exists()
        or Postulante.objects.filter(dni=data["datos"]["dni"]).exists()
    ):
        return None
    user = get_user_model()(username=uuid4().hex, email=correo, is_active=False)
    comprobar_password(data["password"], user)
    user.set_password(data["password"])
    user.save()
    persona = Postulante.objects.create(**data["datos"])
    identidad = IdentidadAcceso.objects.create(
        usuarioid=user,
        correo=correo,
        postulanteid=persona,
        aviso_version=data["aviso_version"],
        aviso_aceptado_en=timezone.now(),
    )
    grupo, _ = Group.objects.get_or_create(name="users")
    user.groups.add(grupo)
    return identidad


def _aviso(proceso, data):
    if data["aviso_version"] != proceso.aviso_version:
        raise ValidationError(
            {"aviso_version": "Debe leer la versión vigente del aviso."}
        )


@transaction.atomic
def registrar(data):
    proceso = _proceso(data["codigo"])
    if proceso.modalidad != ProcesoEvaluacion.Modalidad.ENLACE:
        raise Conflicto("Este proceso requiere invitación individual.")
    _aviso(proceso, data)
    _bloquear_correo("dni:" + data["datos"]["dni"])
    _bloquear_correo(data["correo"])
    identidad = _nueva_identidad(data)
    if identidad:
        _encolar(
            AccionCorreo.Tipo.VERIFICAR,
            identidad.correo,
            identidad=identidad,
            proceso=proceso,
        )
    return MENSAJE_CORREO


def _asignar(proceso, identidad, invitacion=None):
    proceso_vigente(proceso)
    if invitacion is not None:
        _validar_invitacion(invitacion, identidad.correo, proceso)
    elif proceso.modalidad != ProcesoEvaluacion.Modalidad.ENLACE:
        raise Conflicto("Debe aceptar la invitación individual.")
    if (
        not identidad.acceso_confirmado
        or not identidad.usuarioid.is_active
        or not identidad.postulanteid_id
    ):
        raise Conflicto("La cuenta no está habilitada para participar.")
    existente = AsignacionEvaluacion.objects.filter(
        procesoid=proceso, identidadid=identidad
    ).first()
    if existente:
        if not existente.activa:
            raise Conflicto("La asignación está revocada.")
        return existente
    evaluacion = Evaluacion.objects.create(postulanteid=identidad.postulanteid)
    return AsignacionEvaluacion.objects.create(
        procesoid=proceso,
        identidadid=identidad,
        evaluacionid=evaluacion,
        invitacionid=invitacion,
        aviso_version=proceso.aviso_version,
        aviso_aceptado_en=timezone.now(),
    )


@transaction.atomic
def verificar_correo(token):
    previa = _leer_accion(token, AccionCorreo.Tipo.VERIFICAR)
    proceso = (
        ProcesoEvaluacion.objects.select_for_update().get(pk=previa.procesoid_id)
        if previa.procesoid_id
        else None
    )
    identidad = IdentidadAcceso.objects.select_for_update().get(
        pk=previa.identidadid_id
    )
    accion = _accion_bloqueada(previa)
    if identidad.correo_verificado or identidad.desactivada_en:
        raise ValidationError("Enlace inválido o vencido.")
    identidad.correo_verificado = True
    identidad.save(update_fields=["correo_verificado"])
    user = identidad.usuarioid
    user.is_active = True
    user.save(update_fields=["is_active"])
    accion.usada_en = timezone.now()
    accion.save(update_fields=["usada_en"])
    if (
        proceso is not None
        and _esta_vigente(proceso)
        and proceso.modalidad == ProcesoEvaluacion.Modalidad.ENLACE
        and identidad.aviso_version == proceso.aviso_version
    ):
        return _asignar(proceso, identidad)
    return None


@transaction.atomic
def participar(user, codigo, aviso_version):
    proceso = _proceso(codigo)
    if aviso_version != proceso.aviso_version:
        raise ValidationError("Debe leer el aviso vigente.")
    identidad = IdentidadAcceso.objects.select_for_update().get(usuarioid=user)
    if proceso.modalidad == ProcesoEvaluacion.Modalidad.INDIVIDUAL:
        raise Conflicto("Debe aceptar la invitación individual.")
    return _asignar(proceso, identidad)


@transaction.atomic
def invitar(user, proceso, correo, *, manual=False):
    proceso = _proceso(proceso.codigo)
    if proceso.modalidad != ProcesoEvaluacion.Modalidad.INDIVIDUAL:
        raise Conflicto("El proceso usa un enlace compartible.")
    invitacion, _ = Invitacion.objects.get_or_create(
        procesoid=proceso,
        correo=correo,
        defaults={
            "creada_por": user,
            "vence_en": min(proceso.fin, timezone.now() + timedelta(hours=72)),
        },
    )
    if invitacion.aceptada_en:
        raise Conflicto("La invitación ya fue aceptada; gestione la asignación.")
    invitacion.revocada = False
    invitacion.vence_en = min(proceso.fin, timezone.now() + timedelta(hours=72))
    invitacion.save(update_fields=["revocada", "vence_en"])
    _encolar(
        AccionCorreo.Tipo.INVITAR,
        correo,
        proceso=proceso,
        invitacion=invitacion,
        manual=manual,
    )
    auditar(
        user,
        invitacion,
        "Invitación manual emitida." if manual else "Invitación emitida o reenviada.",
    )
    return invitacion


@transaction.atomic
def emitir_enlace_manual(user, proceso, correo):
    from .enlaces import construir_enlace

    invitacion = invitar(user, proceso, correo, manual=True)
    accion = AccionCorreo.objects.get(
        invitacionid=invitacion, entrega_manual=True, usada_en__isnull=True
    )
    return {
        "id": str(invitacion.pk),
        "enlace": construir_enlace(accion),
        "vence_en": accion.vence_en,
        "canal": "manual",
    }


@transaction.atomic
def revocar_invitacion(invitacion, user=None):
    ProcesoEvaluacion.objects.select_for_update().get(pk=invitacion.procesoid_id)
    invitacion = Invitacion.objects.select_for_update().get(pk=invitacion.pk)
    if invitacion.aceptada_en:
        raise Conflicto("La invitación ya fue aceptada; gestione la asignación.")
    invitacion.revocada = True
    invitacion.save(update_fields=["revocada"])
    AccionCorreo.objects.filter(invitacionid=invitacion, usada_en__isnull=True).update(
        usada_en=timezone.now()
    )
    if user:
        auditar(user, invitacion, "Invitación revocada.")


def _validar_invitacion(invitacion, correo, proceso):
    if proceso.modalidad != ProcesoEvaluacion.Modalidad.INDIVIDUAL:
        raise Conflicto("El proceso usa un enlace compartible.")
    if (
        invitacion.procesoid_id != proceso.pk
        or invitacion.revocada
        or invitacion.aceptada_en
        or invitacion.vence_en <= timezone.now()
        or invitacion.correo != correo
    ):
        raise ValidationError("Enlace inválido o vencido.")


def _invitacion(accion, correo, proceso):
    invitacion = Invitacion.objects.select_for_update().get(pk=accion.invitacionid_id)
    _validar_invitacion(invitacion, correo, proceso)
    return invitacion


def _consumir_invitacion(accion, invitacion):
    ahora = timezone.now()
    accion.usada_en = ahora
    accion.save(update_fields=["usada_en"])
    invitacion.aceptada_en = ahora
    invitacion.save(update_fields=["aceptada_en"])


@transaction.atomic
@sensitive_variables("token")
def consultar_invitacion(token):
    """Comprueba el enlace sin aceptar, consumir ni crear una cuenta."""
    previa = _leer_accion(token, AccionCorreo.Tipo.INVITAR)
    proceso = _proceso(previa.procesoid.codigo)
    accion = _accion_bloqueada(previa)
    invitacion = _invitacion(accion, accion.correo, proceso)
    return proceso, min(accion.vence_en, invitacion.vence_en)


@transaction.atomic
def activar_invitacion(data):
    previa = _leer_accion(data["token"], AccionCorreo.Tipo.INVITAR)
    proceso = _proceso(previa.procesoid.codigo)
    if proceso.codigo != data["codigo"]:
        raise ValidationError("Enlace inválido o vencido.")
    _aviso(proceso, data)
    _bloquear_correo("dni:" + data["datos"]["dni"])
    _bloquear_correo(data["correo"])
    accion = _accion_bloqueada(previa)
    invitacion = _invitacion(accion, data["correo"], proceso)
    identidad = _nueva_identidad(data)
    if identidad is None:
        return MENSAJE_ACTIVACION
    identidad.correo_verificado = not accion.entrega_manual
    identidad.activacion_manual = accion.entrega_manual
    identidad.save(update_fields=["correo_verificado", "activacion_manual"])
    identidad.usuarioid.is_active = True
    identidad.usuarioid.save(update_fields=["is_active"])
    _asignar(proceso, identidad, invitacion)
    _consumir_invitacion(accion, invitacion)
    return MENSAJE_ACTIVACION


@transaction.atomic
def aceptar_invitacion(user, token, aviso_version):
    previa = _leer_accion(token, AccionCorreo.Tipo.INVITAR)
    proceso = _proceso(previa.procesoid.codigo)
    if aviso_version != proceso.aviso_version:
        raise ValidationError("Debe leer el aviso vigente.")
    identidad = IdentidadAcceso.objects.select_for_update().get(usuarioid=user)
    accion = _accion_bloqueada(previa)
    invitacion = _invitacion(accion, identidad.correo, proceso)
    asignacion = _asignar(proceso, identidad, invitacion)
    _consumir_invitacion(accion, invitacion)
    return asignacion


@transaction.atomic
def solicitar_correo(correo, codigo=None):
    identidad = (
        IdentidadAcceso.objects.select_for_update().filter(correo=correo).first()
    )
    if identidad is None or identidad.desactivada_en:
        return MENSAJE_CORREO
    if identidad.correo_verificado and identidad.usuarioid.is_active:
        _encolar(AccionCorreo.Tipo.RECUPERAR, correo, identidad=identidad)
    elif not identidad.correo_verificado:
        _encolar(AccionCorreo.Tipo.VERIFICAR, correo, identidad=identidad)
    return MENSAJE_CORREO


@transaction.atomic
def restablecer(token, password):
    previa = _leer_accion(token, AccionCorreo.Tipo.RECUPERAR)
    identidad = IdentidadAcceso.objects.select_for_update().get(
        pk=previa.identidadid_id
    )
    user = get_user_model().objects.select_for_update().get(pk=identidad.usuarioid_id)
    accion = _accion_bloqueada(previa)
    confirmada = identidad.correo_verificado or (
        accion.entrega_manual and identidad.activacion_manual
    )
    if not user.is_active or not confirmada or identidad.desactivada_en:
        raise ValidationError("Enlace inválido o vencido.")
    comprobar_password(password, user)
    user.set_password(password)
    user.save(update_fields=["password"])
    AccionCorreo.objects.filter(identidadid=identidad, usada_en__isnull=True).update(
        usada_en=timezone.now()
    )
    accion.usada_en = timezone.now()


@transaction.atomic
def renovar(raw):
    try:
        previo = RefreshToken(raw)
        OutstandingToken.objects.select_for_update().get(jti=previo["jti"])
        token = RefreshToken(raw)
        user = JWTAuthentication().get_user(token)
        if not IdentidadAcceso.objects.habilitadas().filter(usuarioid=user).exists():
            raise InvalidToken("Cuenta no habilitada.")
        token.blacklist()
        nuevo = RefreshToken.for_user(user)
        return {"access": str(nuevo.access_token), "refresh": str(nuevo)}
    except (TokenError, OutstandingToken.DoesNotExist) as exc:
        raise InvalidToken("Token inválido o vencido.") from exc


@transaction.atomic
def cerrar_sesion(user, raw):
    try:
        token = RefreshToken(raw)
        OutstandingToken.objects.select_for_update().get(jti=token["jti"])
        token = RefreshToken(raw)
        if str(token["user_id"]) != str(user.pk):
            raise ValidationError("Token inválido.")
        token.blacklist()
    except (TokenError, OutstandingToken.DoesNotExist) as exc:
        raise InvalidToken("Token inválido o vencido.") from exc


AVISO_PERSONAL = "personal-interno"


@transaction.atomic
@sensitive_variables("password")
def crear_gestor(
    *, correo, first_name="", last_name="", superusuario=False, password=None
):
    """Cuenta de personal con login por correo; sin contraseña recibe un enlace después."""
    correo = correo.strip().lower()
    _bloquear_correo(correo)
    if (
        IdentidadAcceso.objects.filter(correo=correo).exists()
        or get_user_model().objects.filter(email__iexact=correo).exists()
    ):
        raise Conflicto("El correo ya está registrado.")
    usuario = get_user_model()(
        username=uuid4().hex,
        email=correo,
        first_name=first_name,
        last_name=last_name,
        is_staff=True,
        is_superuser=superusuario,
        is_active=True,
    )
    if password is None:
        usuario.set_unusable_password()
    else:
        comprobar_password(password, usuario)
        usuario.set_password(password)
    usuario.save()
    if not superusuario:
        usuario.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="accesos", codename="gestionar_accesos"
            )
        )
    return IdentidadAcceso.objects.create(
        usuarioid=usuario,
        correo=correo,
        activacion_manual=True,
        aviso_version=AVISO_PERSONAL,
    )


@transaction.atomic
def vincular_gestor(*, usuario, correo):
    correo = correo.strip().lower()
    _bloquear_correo(correo)
    usuario = get_user_model().objects.select_for_update().get(pk=usuario.pk)
    if not usuario.is_staff:
        raise Conflicto("Solo se vinculan cuentas de personal.")
    if IdentidadAcceso.objects.filter(usuarioid=usuario).exists():
        raise Conflicto("El usuario ya tiene correo de acceso.")
    if (
        IdentidadAcceso.objects.filter(correo=correo).exists()
        or get_user_model()
        .objects.filter(email__iexact=correo)
        .exclude(pk=usuario.pk)
        .exists()
    ):
        raise Conflicto("El correo ya está registrado.")
    usuario.email = correo
    usuario.save(update_fields=["email"])
    return IdentidadAcceso.objects.create(
        usuarioid=usuario,
        correo=correo,
        activacion_manual=True,
        aviso_version=AVISO_PERSONAL,
    )


@transaction.atomic
def emitir_enlace_gestor(user, identidad):
    from .enlaces import construir_enlace

    identidad = IdentidadAcceso.objects.select_for_update().get(pk=identidad.pk)
    if identidad.desactivada_en:
        raise Conflicto("La cuenta está desactivada.")
    accion = _encolar(
        AccionCorreo.Tipo.RECUPERAR, identidad.correo, identidad=identidad, manual=True
    )
    auditar(user, identidad, "Enlace de contraseña emitido.")
    return {"enlace": construir_enlace(accion), "vence_en": accion.vence_en}


def _revocar_sesiones(usuario):
    for token in OutstandingToken.objects.filter(
        user=usuario, blacklistedtoken__isnull=True
    ):
        BlacklistedToken.objects.get_or_create(token=token)


@transaction.atomic
def desactivar_identidad(identidad, user):
    identidad = IdentidadAcceso.objects.select_for_update().get(pk=identidad.pk)
    if identidad.desactivada_en:
        return
    ahora = timezone.now()
    identidad.desactivada_en = ahora
    identidad.save(update_fields=["desactivada_en"])
    usuario = identidad.usuarioid
    usuario.is_active = False
    usuario.save(update_fields=["is_active"])
    AccionCorreo.objects.filter(identidadid=identidad, usada_en__isnull=True).update(
        usada_en=ahora
    )
    _revocar_sesiones(usuario)
    auditar(user, identidad, "Cuenta desactivada.")


@transaction.atomic
def reactivar_identidad(identidad, user):
    identidad = IdentidadAcceso.objects.select_for_update().get(pk=identidad.pk)
    if not identidad.desactivada_en:
        return
    identidad.desactivada_en = None
    identidad.save(update_fields=["desactivada_en"])
    usuario = identidad.usuarioid
    usuario.is_active = identidad.acceso_confirmado
    usuario.save(update_fields=["is_active"])
    auditar(user, identidad, "Cuenta reactivada.")


@transaction.atomic
def revocar_asignacion(asignacion, user):
    ProcesoEvaluacion.objects.select_for_update().get(pk=asignacion.procesoid_id)
    asignacion = AsignacionEvaluacion.objects.select_for_update().get(pk=asignacion.pk)
    asignacion.activa = False
    asignacion.save(update_fields=["activa"])
    auditar(user, asignacion, "Asignación revocada.")


@transaction.atomic
def enviar_respuestas(user, asignacion_id, items):
    previa = AsignacionEvaluacion.objects.filter(
        pk=asignacion_id, identidadid__usuarioid=user
    ).first()
    if previa is None:
        raise NotFound()
    proceso = _proceso(previa.procesoid.codigo)
    asignacion = AsignacionEvaluacion.objects.select_for_update().get(pk=previa.pk)
    if not asignacion.activa:
        raise Conflicto("La asignación está revocada.")
    proceso_vigente(proceso)
    return registrar_respuestas(asignacion.evaluacionid, items)


@transaction.atomic
def eliminar_proceso(user, proceso):
    from django.db.models import ProtectedError

    proceso = ProcesoEvaluacion.objects.select_for_update().get(pk=proceso.pk)
    LogEntry.objects.log_actions(
        user_id=user.pk,
        queryset=[proceso],
        action_flag=DELETION,
        change_message="Proceso eliminado.",
    )
    try:
        proceso.delete()
    except ProtectedError as exc:
        raise Conflicto(
            "El proceso ya tiene registros, invitaciones o participantes; "
            "ciérrelo con activo=false."
        ) from exc


def cambiar_correo(identidad, correo):
    if correo == identidad.correo:
        return
    _bloquear_correo(correo)
    usuario = identidad.usuarioid
    if (
        IdentidadAcceso.objects.filter(correo=correo).exclude(pk=identidad.pk).exists()
        or get_user_model()
        .objects.filter(email__iexact=correo)
        .exclude(pk=usuario.pk)
        .exists()
    ):
        raise Conflicto("El correo ya está en uso.")
    identidad.correo = correo
    identidad.save(update_fields=["correo"])
    usuario.email = correo
    usuario.save(update_fields=["email"])
    AccionCorreo.objects.filter(identidadid=identidad, usada_en__isnull=True).update(
        usada_en=timezone.now()
    )
    _revocar_sesiones(usuario)


def corregir_ficha(identidad, datos):
    ficha = Postulante.objects.select_for_update().get(pk=identidad.postulanteid_id)
    dni = datos.get("dni")
    if dni and dni != ficha.dni:
        _bloquear_correo("dni:" + dni)
        if Postulante.objects.filter(dni=dni).exclude(pk=ficha.pk).exists():
            raise Conflicto("El DNI ya está registrado.")
    for campo, valor in datos.items():
        setattr(ficha, campo, valor)
    ficha.save()


def _actividad(identidad):
    usuario = identidad.usuarioid

    if LogEntry.objects.filter(user=usuario).exists():
        return True
    if identidad.postulanteid_id is None:
        return (
            ProcesoEvaluacion.objects.filter(creado_por=usuario).exists()
            or Invitacion.objects.filter(creada_por=usuario).exists()
        )
    return (
        AsignacionEvaluacion.objects.filter(identidadid=identidad).exists()
        or Evaluacion.objects.filter(postulanteid=identidad.postulanteid_id).exists()
    )


@transaction.atomic
def eliminar_identidad(identidad, user):
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import ProtectedError

    from .fotos import (
        AlmacenamientoNoDisponible,
        BotoCoreError,
        ClientError,
        cliente_s3,
    )
    from .models import FotoParticipante

    identidad = IdentidadAcceso.objects.select_for_update().get(pk=identidad.pk)
    if _actividad(identidad):
        raise Conflicto(
            "La cuenta tiene actividad registrada; desactívela en lugar de borrarla."
        )
    usuario = identidad.usuarioid
    ficha = identidad.postulanteid
    foto = FotoParticipante.objects.filter(identidadid=identidad).first()
    LogEntry.objects.create(
        user_id=user.pk,
        content_type=ContentType.objects.get_for_model(IdentidadAcceso),
        object_id=str(identidad.pk),
        object_repr="Participante eliminado" if ficha else "Gestor eliminado",
        action_flag=DELETION,
        change_message="Cuenta eliminada.",
    )
    try:
        AccionCorreo.objects.filter(identidadid=identidad).delete()
        if foto:
            foto.delete()
        identidad.delete()
        if ficha:
            ficha.delete()
        OutstandingToken.objects.filter(user=usuario).delete()
        usuario.delete()
    except ProtectedError as exc:
        raise Conflicto(
            "La cuenta tiene actividad registrada; desactívela en lugar de borrarla."
        ) from exc
    if foto:
        try:
            cliente_s3(foto.region).delete_object(Bucket=foto.bucket, Key=foto.clave)
        except (BotoCoreError, ClientError) as exc:
            raise AlmacenamientoNoDisponible() from exc
