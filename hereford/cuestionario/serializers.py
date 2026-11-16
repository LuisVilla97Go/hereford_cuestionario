import re
from rest_framework import serializers
from .models import AreaVocacional, Evaluacion, Postulante, Pregunta, ResultadoArea


class EnteroEstricto(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int:
            self.fail("invalid")
        return super().to_internal_value(data)


class PostulanteSerializer(serializers.ModelSerializer):
    genero = serializers.ChoiceField(choices=["M", "F"])

    class Meta:
        model = Postulante
        fields = [
            "id",
            "dni",
            "nombre_completo",
            "apellido_paterno",
            "apellido_materno",
            "nombres",
            "genero",
            "tipo_institucion",
            "tipo_gestion",
            "tipo_estudio",
            "anios_inversion",
            "modalidad_estudio",
            "creado_en",
        ]
        read_only_fields = ["id", "nombre_completo", "creado_en"]

    def validate_dni(self, value):
        if re.fullmatch(r"[0-9]{8,20}", value) is None:
            raise serializers.ValidationError("Debe contener de 8 a 20 dígitos ASCII.")
        return value


class AreaVocacionalSerializer(serializers.ModelSerializer):
    class Meta:
        model = AreaVocacional
        fields = ["id", "codigo", "nombre", "comentario"]
        read_only_fields = fields


class PreguntaSerializer(serializers.ModelSerializer):
    area = serializers.CharField(source="areaid.codigo", read_only=True)
    nombre_area = serializers.CharField(source="areaid.nombre", read_only=True)

    class Meta:
        model = Pregunta
        fields = ["numero", "enunciado", "area", "nombre_area"]
        read_only_fields = fields


class RespuestaItemSerializer(serializers.Serializer):
    pregunta = EnteroEstricto(min_value=1, max_value=90)
    valor = EnteroEstricto(min_value=1, max_value=5)


class EnviarRespuestasSerializer(serializers.Serializer):
    respuestas = RespuestaItemSerializer(many=True, min_length=90, max_length=90)

    def validate_respuestas(self, value):
        if sorted(item["pregunta"] for item in value) != list(range(1, 91)):
            raise serializers.ValidationError(
                "Se requieren preguntas 1–90 sin repetir."
            )
        return value


class EvaluacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evaluacion
        fields = ["id", "postulanteid", "fecha_evaluacion", "completado"]
        read_only_fields = ["id", "fecha_evaluacion", "completado"]


class ResultadoAreaSerializer(serializers.ModelSerializer):
    area = serializers.CharField(source="areaid.codigo", read_only=True)
    nombre_area = serializers.SerializerMethodField()
    puntaje_baremo = serializers.SerializerMethodField()
    tipo_coincidencia = serializers.SerializerMethodField()
    estado_conversion = serializers.SerializerMethodField()
    motivo_pendiente = serializers.SerializerMethodField()

    def get_nombre_area(self, obj):
        return self.context.get("nombres_area", {}).get(
            obj.areaid.codigo, obj.areaid.nombre
        )

    def get_estado_conversion(self, obj):
        anterior = "pendiente_baremo" if obj.percentil is None else "convertido"
        return (
            self.context.get("conversiones", {})
            .get(obj.areaid.codigo, {})
            .get("estado_conversion", anterior)
        )

    def get_motivo_pendiente(self, obj):
        return (
            self.context.get("conversiones", {})
            .get(obj.areaid.codigo, {})
            .get("motivo_pendiente")
        )

    def get_puntaje_baremo(self, obj):
        return (
            self.context.get("conversiones", {})
            .get(obj.areaid.codigo, {})
            .get("puntaje_baremo")
        )

    def get_tipo_coincidencia(self, obj):
        return (
            self.context.get("conversiones", {})
            .get(obj.areaid.codigo, {})
            .get("tipo_coincidencia")
        )

    class Meta:
        model = ResultadoArea
        fields = [
            "area",
            "nombre_area",
            "puntaje_directo",
            "percentil",
            "puntaje_baremo",
            "tipo_coincidencia",
            "estado_conversion",
            "motivo_pendiente",
            "interpretacion",
        ]
        read_only_fields = fields
