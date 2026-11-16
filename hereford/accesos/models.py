from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


def codigo_proceso():
    return uuid4().hex


class IdentidadesQuerySet(models.QuerySet):
    def habilitadas(self):
        return self.filter(models.Q(correo_verificado=True) | models.Q(activacion_manual=True))


class IdentidadAcceso(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    usuarioid = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="usuario_id",
        related_name="identidad_acceso",
    )
    correo = models.EmailField(unique=True)
    correo_verificado = models.BooleanField(default=False)
    activacion_manual = models.BooleanField(default=False)
    objects = IdentidadesQuerySet.as_manager()

    postulanteid = models.OneToOneField(
        "cuestionario.Postulante",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="postulante_id",
        related_name="identidad_acceso",
    )
    aviso_version = models.CharField(max_length=80)
    aviso_aceptado_en = models.DateTimeField(null=True, blank=True)

    @property
    def acceso_confirmado(self):
        return self.correo_verificado or self.activacion_manual

    class Meta:
        db_table = "identidades_acceso"
        constraints = [
            models.UniqueConstraint(Lower("correo"), name="identidad_correo_insensible_unico"),
            models.CheckConstraint(
                condition=models.Q(correo=Lower("correo")), name="identidad_correo_minusculas"
            ),
        ]


class ProcesoEvaluacion(models.Model):
    class Modalidad(models.TextChoices):
        ENLACE = "enlace", "Enlace compartible"
        INDIVIDUAL = "individual", "Invitación individual"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    codigo = models.CharField(max_length=32, unique=True, default=codigo_proceso, editable=False)
    titulo = models.CharField(max_length=180)
    descripcion = models.TextField(blank=True)
    instrucciones = models.TextField()
    aviso_version = models.CharField(max_length=80)
    aviso_privacidad = models.TextField()
    inicio = models.DateTimeField()
    fin = models.DateTimeField()
    activo = models.BooleanField(default=False)
    modalidad = models.CharField(max_length=10, choices=Modalidad, default=Modalidad.ENLACE)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        db_table = "procesos_evaluacion"
        ordering = ["-inicio", "id"]
        permissions = [("gestionar_accesos", "Gestionar procesos, invitaciones y asignaciones")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(fin__gt=models.F("inicio")), name="proceso_ventana_valida"
            ),
            models.CheckConstraint(
                condition=models.Q(modalidad__in=["enlace", "individual"]),
                name="proceso_modalidad_valida",
            ),
        ]

    def __str__(self):
        return self.titulo


class Invitacion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    procesoid = models.ForeignKey(
        ProcesoEvaluacion, on_delete=models.PROTECT, db_column="proceso_id"
    )
    correo = models.EmailField()
    vence_en = models.DateTimeField()
    revocada = models.BooleanField(default=False)
    aceptada_en = models.DateTimeField(null=True, blank=True)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        db_table = "invitaciones_evaluacion"
        constraints = [
            models.UniqueConstraint(
                fields=["procesoid", "correo"], name="invitacion_proceso_correo_unico"
            )
        ]


class AsignacionEvaluacion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    procesoid = models.ForeignKey(
        ProcesoEvaluacion, on_delete=models.PROTECT, db_column="proceso_id"
    )
    identidadid = models.ForeignKey(
        IdentidadAcceso, on_delete=models.PROTECT, db_column="identidad_id"
    )
    evaluacionid = models.OneToOneField(
        "cuestionario.Evaluacion",
        on_delete=models.PROTECT,
        db_column="evaluacion_id",
        related_name="asignacion_acceso",
    )
    invitacionid = models.OneToOneField(
        Invitacion, on_delete=models.PROTECT, null=True, blank=True, db_column="invitacion_id"
    )
    activa = models.BooleanField(default=True)
    aviso_version = models.CharField(max_length=80)
    aviso_aceptado_en = models.DateTimeField()
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "asignaciones_evaluacion"
        ordering = ["-creada_en", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["procesoid", "identidadid"], name="asignacion_proceso_identidad_unica"
            )
        ]


class AccionCorreo(models.Model):
    """Bandeja transaccional. El secreto se firma al despachar, no se guarda en texto."""

    class Tipo(models.TextChoices):
        VERIFICAR = "verificar", "Verificar correo"
        RECUPERAR = "recuperar", "Restablecer contraseña"
        INVITAR = "invitar", "Invitación"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    tipo = models.CharField(max_length=10, choices=Tipo)
    correo = models.EmailField()
    identidadid = models.ForeignKey(
        IdentidadAcceso, on_delete=models.PROTECT, null=True, blank=True, db_column="identidad_id"
    )
    procesoid = models.ForeignKey(
        ProcesoEvaluacion, on_delete=models.PROTECT, db_column="proceso_id", null=True, blank=True
    )
    invitacionid = models.ForeignKey(
        Invitacion, on_delete=models.PROTECT, null=True, blank=True, db_column="invitacion_id"
    )
    credencial_version = models.CharField(max_length=128, blank=True)
    entrega_manual = models.BooleanField(default=False)
    vence_en = models.DateTimeField()
    usada_en = models.DateTimeField(null=True, blank=True)
    enviada_en = models.DateTimeField(null=True, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "acciones_correo"
        ordering = ["creada_en", "id"]
        indexes = [
            models.Index(fields=["enviada_en", "usada_en", "vence_en"], name="correo_pendiente_idx")
        ]


class LimiteAcceso(models.Model):
    """Contador compartido entre workers; claves HMAC, nunca correo/IP en claro."""

    clave = models.CharField(max_length=64, primary_key=True)
    ventana = models.BigIntegerField()
    intentos = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "limites_acceso"


class FotoParticipante(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    identidadid = models.OneToOneField(
        IdentidadAcceso, on_delete=models.PROTECT, db_column="identidad_id", related_name="foto"
    )
    bucket = models.CharField(max_length=63)
    region = models.CharField(max_length=32)
    clave = models.CharField(max_length=255, unique=True)
    tamano = models.PositiveIntegerField()
    ancho = models.PositiveSmallIntegerField()
    alto = models.PositiveSmallIntegerField()
    aceptada_en = models.DateTimeField()

    class Meta:
        db_table = "fotos_participante"