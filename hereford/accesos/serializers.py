from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from cuestionario.serializers import PostulanteSerializer

from .models import AsignacionEvaluacion, Invitacion, ProcesoEvaluacion


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
