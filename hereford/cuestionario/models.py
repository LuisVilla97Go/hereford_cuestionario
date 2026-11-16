from uuid import uuid4

from django.core.validators import (
    MaxValueValidator,
    MinLengthValidator,
    MinValueValidator,
)
from django.db import models


class Postulante(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    dni = models.CharField(max_length=20, unique=True, validators=[MinLengthValidator(8)])
    nombre_completo = models.TextField(blank=True, null=True)
    apellido_paterno = models.TextField()
    apellido_materno = models.TextField()
    nombres = models.TextField()
    genero = models.TextField()
    tipo_institucion = models.TextField(blank=True, null=True)
    tipo_gestion = models.TextField(blank=True, null=True)
    tipo_estudio = models.TextField(blank=True, null=True)
    anios_inversion = models.TextField(blank=True, null=True)
    modalidad_estudio = models.TextField(blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "postulantes"

    def save(self, *args, **kwargs):
        self.nombre_completo = (
            f"{self.apellido_paterno} {self.apellido_materno} {self.nombres}".strip()
        )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre_completo


class AreaVocacional(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    codigo = models.TextField(unique=True)
    nombre = models.TextField()
    comentario = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "areas_vocacionales"

    def __str__(self):
        return self.nombre


class Pregunta(models.Model):
    numero = models.PositiveSmallIntegerField(primary_key=True)
    enunciado = models.TextField()
    areaid = models.ForeignKey(
        to=AreaVocacional,
        on_delete=models.PROTECT,
        db_column="area_id",
        related_name="preguntas",
    )

    class Meta:
        db_table = "preguntas"
        ordering = ["numero"]

    def __str__(self):
        return f"{self.numero}. {self.enunciado}"


class Evaluacion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    postulanteid = models.ForeignKey(
        to=Postulante,
        on_delete=models.CASCADE,
        db_column="postulante_id",
        related_name="evaluaciones",
    )
    fecha_evaluacion = models.DateTimeField(auto_now_add=True)
    completado = models.BooleanField(default=False)

    class Meta:
        db_table = "evaluaciones"

    def __str__(self):
        return f"Evaluación de {self.postulanteid.nombre_completo}"


class Respuesta(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    evaluacionid = models.ForeignKey(
        to=Evaluacion,
        on_delete=models.CASCADE,
        db_column="evaluacion_id",
        related_name="respuestas",
    )
    preguntaid = models.ForeignKey(
        to=Pregunta,
        on_delete=models.PROTECT,
        db_column="pregunta_id",
        related_name="respuestas",
    )
    valor = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )

    class Meta:
        db_table = "respuestas"
        unique_together = ("evaluacionid", "preguntaid")

    def __str__(self):
        return f"Pregunta {self.preguntaid_id}: {self.valor}"


class ResultadoArea(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    evaluacionid = models.ForeignKey(
        to=Evaluacion,
        on_delete=models.CASCADE,
        db_column="evaluacion_id",
        related_name="resultados",
    )
    areaid = models.ForeignKey(
        to=AreaVocacional,
        on_delete=models.PROTECT,
        db_column="area_id",
        related_name="resultados",
    )
    puntaje_directo = models.PositiveSmallIntegerField()
    percentil = models.PositiveSmallIntegerField(null=True, blank=True)
    interpretacion = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "resultados_area"
        unique_together = ("evaluacionid", "areaid")

    def __str__(self):
        valor = f"P{self.percentil}" if self.percentil is not None else "percentil pendiente"
        return f"{self.areaid.nombre}: {valor}"


class RegistroCalificacion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    evaluacionid = models.OneToOneField(
        Evaluacion,
        on_delete=models.CASCADE,
        db_column="evaluacion_id",
        related_name="registro_calificacion",
    )
    catalogo_sha256 = models.CharField(max_length=64)
    genero_baremo = models.CharField(max_length=1)
    algoritmo = models.CharField(max_length=80)
    snapshot = models.JSONField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "registros_calificacion"


class Baremo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    areaid = models.ForeignKey(
        AreaVocacional,
        on_delete=models.PROTECT,
        db_column="area_id",
        related_name="baremos",
    )
    genero = models.CharField(max_length=1, choices=[("M", "M"), ("F", "F")])
    version = models.CharField(max_length=64)
    regla = models.CharField(max_length=40, default="mas_cercano_empate_inferior")
    no_encontrado = models.PositiveSmallIntegerField()
    validado = models.BooleanField(default=False)
    poblacion_normativa = models.JSONField(null=True, blank=True)
    procedencia = models.JSONField()

    class Meta:
        db_table = "baremos"
        constraints = [
            models.UniqueConstraint(fields=["areaid", "genero"], name="baremo_area_genero_unico"),
            models.CheckConstraint(
                condition=models.Q(genero__in=["M", "F"]), name="baremo_genero_m_f"
            ),
            models.CheckConstraint(
                condition=models.Q(no_encontrado__gte=1, no_encontrado__lte=99),
                name="baremo_salida_1_99",
            ),
        ]


class PuntoBaremo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    baremoid = models.ForeignKey(
        Baremo, on_delete=models.CASCADE, db_column="baremo_id", related_name="puntos"
    )
    puntaje_directo = models.PositiveSmallIntegerField()
    percentil = models.PositiveSmallIntegerField()
    celda_origen = models.CharField(max_length=40, blank=True)

    class Meta:
        db_table = "puntos_baremo"
        ordering = ["-percentil"]
        constraints = [
            models.UniqueConstraint(
                fields=["baremoid", "percentil"], name="punto_baremo_percentil_unico"
            ),
            models.CheckConstraint(
                condition=models.Q(puntaje_directo__gte=10, puntaje_directo__lte=50),
                name="punto_baremo_directo_10_50",
            ),
            models.CheckConstraint(
                condition=models.Q(percentil__gte=1, percentil__lte=99),
                name="punto_baremo_percentil_1_99",
            ),
        ]
