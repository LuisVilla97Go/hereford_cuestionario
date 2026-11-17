from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from cuestionario.serializers import PostulanteSerializer

from .models import (
    AsignacionEvaluacion,
    IdentidadAcceso,
    Invitacion,
    Organizacion,
    Pago,
    ProcesoEvaluacion,
)


class EntradaEstricta(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["Hay campos no permitidos."]})
        return super().to_internal_value(data)


class CorreoSerializer(EntradaEstricta):
    correo = serializers.EmailField(max_length=254)

    def validate_correo(self, value):
        return value.strip().lower()


class LoginSerializer(CorreoSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=256)


class FotoEntradaSerializer(EntradaEstricta):
    foto = serializers.FileField()
    foto_consentida = serializers.BooleanField()

    def validate_foto_consentida(self, value):
        if not value:
            raise serializers.ValidationError("La foto es opcional; confirme que desea subirla.")
        return value


class DatosRegistroSerializer(PostulanteSerializer):
    class Meta(PostulanteSerializer.Meta):
        fields = ["dni", "nombres", "apellido_paterno", "apellido_materno", "genero"]
        read_only_fields = []
        extra_kwargs = {"dni": {"validators": []}}

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError(
                {"non_field_errors": ["Hay campos no permitidos en los datos personales."]}
            )
        return super().to_internal_value(data)


class RegistroSerializer(CorreoSerializer):
    codigo = serializers.CharField(max_length=32)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=256)
    datos = DatosRegistroSerializer()
    aviso_version = serializers.CharField(max_length=80)
    aviso_leido = serializers.BooleanField()

    def validate_aviso_leido(self, value):
        if value is not True:
            raise serializers.ValidationError("Debe confirmar la lectura del aviso del proceso.")
        return value


class TokenSerializer(EntradaEstricta):
    token = serializers.CharField(write_only=True, max_length=512)


class ActivacionSerializer(RegistroSerializer):
    token = serializers.CharField(write_only=True, max_length=512)


class RestablecerSerializer(TokenSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=256)


class RecuperarSerializer(CorreoSerializer):
    codigo = serializers.CharField(max_length=32, required=False)


class AceptarSerializer(TokenSerializer):
    aviso_version = serializers.CharField(max_length=80)
    aviso_leido = serializers.BooleanField()

    def validate_aviso_leido(self, value):
        if value is not True:
            raise serializers.ValidationError("Debe confirmar la lectura del aviso.")
        return value


class ParticiparSerializer(EntradaEstricta):
    aviso_version = serializers.CharField(max_length=80)
    aviso_leido = serializers.BooleanField()

    def validate_aviso_leido(self, value):
        if value is not True:
            raise serializers.ValidationError("Debe confirmar la lectura del aviso.")
        return value


def comprobar_password(password, user):
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"password": exc.messages}) from exc


class RefreshSerializer(EntradaEstricta):
    refresh = serializers.CharField(write_only=True, max_length=4096)


class ProcesoPublicoSerializer(serializers.ModelSerializer):
    instrumento = serializers.SerializerMethodField()

    def get_instrumento(self, obj):
        return "Hereford: 90 preguntas; escala 1 a 5. Orientación vocacional."

    class Meta:
        model = ProcesoEvaluacion
        fields = [
            "codigo",
            "titulo",
            "descripcion",
            "instrucciones",
            "inicio",
            "fin",
            "activo",
            "modalidad",
            "aviso_version",
            "aviso_privacidad",
            "instrumento",
        ]
        read_only_fields = fields


class ProcesoAdminSerializer(serializers.ModelSerializer):
    organizacionid = serializers.PrimaryKeyRelatedField(
        queryset=Organizacion.objects.filter(activa=True), required=False, allow_null=True
    )

    class Meta:
        model = ProcesoEvaluacion
        fields = [
            "id",
            "codigo",
            "titulo",
            "descripcion",
            "instrucciones",
            "aviso_version",
            "aviso_privacidad",
            "inicio",
            "fin",
            "activo",
            "modalidad",
            "organizacionid",
        ]
        read_only_fields = ["id", "codigo"]

    def validate(self, attrs):
        inicio = attrs.get("inicio", getattr(self.instance, "inicio", None))
        fin = attrs.get("fin", getattr(self.instance, "fin", None))
        if inicio is None or fin is None or fin <= inicio:
            raise serializers.ValidationError("La fecha final debe ser posterior al inicio.")
        return attrs


class InvitacionSerializer(CorreoSerializer):
    procesoid = serializers.PrimaryKeyRelatedField(queryset=ProcesoEvaluacion.objects.all())


class GestorSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source="usuarioid.first_name", read_only=True)
    last_name = serializers.CharField(source="usuarioid.last_name", read_only=True)

    class Meta:
        model = IdentidadAcceso
        fields = ["id", "correo", "first_name", "last_name", "estado"]
        read_only_fields = fields


class GestorAltaSerializer(CorreoSerializer):
    first_name = serializers.CharField(max_length=150, required=False, default="")
    last_name = serializers.CharField(max_length=150, required=False, default="")


class CorreoOpcional(EntradaEstricta):
    correo = serializers.EmailField(max_length=254, required=False)

    def validate_correo(self, value):
        return value.strip().lower()


class GestorEdicionSerializer(CorreoOpcional):
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False)


class ParticipanteSerializer(serializers.ModelSerializer):
    nombres = serializers.CharField(source="postulanteid.nombres", read_only=True)
    apellido_paterno = serializers.CharField(source="postulanteid.apellido_paterno", read_only=True)
    apellido_materno = serializers.CharField(source="postulanteid.apellido_materno", read_only=True)
    asignaciones = serializers.IntegerField(read_only=True)

    class Meta:
        model = IdentidadAcceso
        fields = [
            "id",
            "correo",
            "nombres",
            "apellido_paterno",
            "apellido_materno",
            "estado",
            "activacion_manual",
            "asignaciones",
        ]
        read_only_fields = fields


class ParticipanteEdicionSerializer(CorreoOpcional):
    nombres = serializers.CharField(max_length=150, required=False)
    apellido_paterno = serializers.CharField(max_length=150, required=False)
    apellido_materno = serializers.CharField(max_length=150, required=False)
    dni = serializers.RegexField(r"\A[0-9]{8,20}\Z", required=False)
    genero = serializers.ChoiceField(choices=["M", "F"], required=False)


class InvitacionSalidaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitacion
        fields = ["id", "procesoid", "correo", "vence_en", "revocada", "aceptada_en"]
        read_only_fields = fields


class AsignacionSerializer(serializers.ModelSerializer):
    proceso = ProcesoPublicoSerializer(source="procesoid", read_only=True)
    completado = serializers.BooleanField(source="evaluacionid.completado", read_only=True)

    class Meta:
        model = AsignacionEvaluacion
        fields = ["id", "proceso", "activa", "completado", "creada_en"]
        read_only_fields = fields


class ProcesoClienteSerializer(ProcesoAdminSerializer):
    organizacionid = serializers.PrimaryKeyRelatedField(read_only=True)


class OrganizacionSerializer(serializers.ModelSerializer):
    ruc = serializers.RegexField(r"\A[0-9]{11}\Z", required=False, allow_blank=True)
    cupos_comprados = serializers.IntegerField(read_only=True)
    cupos_usados = serializers.IntegerField(read_only=True)
    cupos_disponibles = serializers.SerializerMethodField()

    class Meta:
        model = Organizacion
        fields = [
            "id",
            "nombre",
            "ruc",
            "activa",
            "es_prueba",
            "creada_en",
            "cupos_comprados",
            "cupos_usados",
            "cupos_disponibles",
        ]
        read_only_fields = ["id", "creada_en"]

    def get_cupos_disponibles(self, obj):
        return obj.cupos_comprados - obj.cupos_usados

    def validate_es_prueba(self, value):
        if self.instance is not None and value != self.instance.es_prueba:
            raise serializers.ValidationError("No se puede cambiar después de crearla.")
        return value


class PagoEntradaSerializer(EntradaEstricta):
    organizacionid = serializers.PrimaryKeyRelatedField(
        queryset=Organizacion.objects.all(), required=False
    )
    correo = serializers.EmailField(max_length=254, required=False)
    procesoid = serializers.PrimaryKeyRelatedField(
        queryset=ProcesoEvaluacion.objects.all(), required=False
    )
    cupos = serializers.IntegerField(min_value=1, max_value=10000, required=False)
    monto = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    moneda = serializers.ChoiceField(choices=Pago.Moneda.choices, default=Pago.Moneda.PEN)
    medio = serializers.ChoiceField(choices=Pago.Medio.choices)
    referencia = serializers.CharField(max_length=120, required=False, default="")
    nota = serializers.CharField(required=False, default="")

    def validate_correo(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        institucion = "organizacionid" in attrs
        persona = "correo" in attrs or "procesoid" in attrs
        if institucion == persona:
            raise serializers.ValidationError(
                "Indique organizacionid (institución) o correo y procesoid (persona)."
            )
        if institucion:
            if "cupos" not in attrs:
                raise serializers.ValidationError({"cupos": "Indique los cupos comprados."})
            return attrs
        if "correo" not in attrs or "procesoid" not in attrs:
            raise serializers.ValidationError("Un pago individual necesita correo y procesoid.")
        if attrs.setdefault("cupos", 1) != 1:
            raise serializers.ValidationError({"cupos": "Un pago individual cubre a una persona."})
        return attrs


class PagoSerializer(serializers.ModelSerializer):
    anulado = serializers.SerializerMethodField()

    class Meta:
        model = Pago
        fields = [
            "id",
            "organizacionid",
            "correo",
            "procesoid",
            "invitacionid",
            "cupos",
            "monto",
            "moneda",
            "medio",
            "referencia",
            "nota",
            "anula",
            "anulado",
            "es_prueba",
            "registrado_en",
        ]
        read_only_fields = fields

    def get_anulado(self, obj):
        try:
            return obj.anulacion is not None
        except Pago.DoesNotExist:
            return False


class AnulacionSerializer(EntradaEstricta):
    nota = serializers.CharField(required=False, default="")


class ClienteSerializer(GestorSerializer):
    organizacionid = serializers.PrimaryKeyRelatedField(read_only=True)
    organizacion = serializers.CharField(source="organizacionid.nombre", read_only=True)

    class Meta(GestorSerializer.Meta):
        fields = [*GestorSerializer.Meta.fields, "organizacionid", "organizacion"]
        read_only_fields = fields


class ClienteAltaSerializer(GestorAltaSerializer):
    organizacionid = serializers.PrimaryKeyRelatedField(
        queryset=Organizacion.objects.filter(activa=True)
    )
