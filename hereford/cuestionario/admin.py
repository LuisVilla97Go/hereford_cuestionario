from django.contrib import admin
from .models import (
    AreaVocacional,
    Baremo,
    Evaluacion,
    Postulante,
    Pregunta,
    PuntoBaremo,
    RegistroCalificacion,
    Respuesta,
    ResultadoArea,
)


class SoloLectura(admin.ModelAdmin):
    list_per_page = 50
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Postulante)
class PostulanteAdmin(SoloLectura):
    list_display = ["nombre_completo", "genero", "creado_en"]
    search_fields = ["nombres", "apellido_paterno", "apellido_materno"]
    list_filter = ["genero"]
    ordering = ["-creado_en", "id"]


@admin.register(AreaVocacional)
class AreaAdmin(SoloLectura):
    list_display = ["codigo", "nombre"]
    search_fields = ["codigo", "nombre"]
    ordering = ["codigo"]


@admin.register(Pregunta)
class PreguntaAdmin(SoloLectura):
    list_display = ["numero", "enunciado", "areaid"]
    search_fields = ["enunciado", "areaid__nombre"]
    list_filter = ["areaid"]
    list_select_related = ["areaid"]


@admin.register(Evaluacion)
class EvaluacionAdmin(SoloLectura):
    list_display = ["id", "postulanteid", "completado", "fecha_evaluacion"]
    list_filter = ["completado", "fecha_evaluacion"]
    list_select_related = ["postulanteid"]
    search_fields = ["postulanteid__nombre_completo"]
    ordering = ["-fecha_evaluacion", "id"]


@admin.register(Respuesta)
class RespuestaAdmin(SoloLectura):
    list_display = ["evaluacionid", "preguntaid", "valor"]
    list_select_related = ["evaluacionid__postulanteid", "preguntaid"]
    list_filter = ["valor"]


@admin.register(ResultadoArea)
class ResultadoAdmin(SoloLectura):
    list_display = ["evaluacionid", "areaid", "puntaje_directo", "percentil"]
    list_select_related = ["evaluacionid__postulanteid", "areaid"]
    list_filter = ["areaid"]


@admin.register(RegistroCalificacion)
class RegistroAdmin(SoloLectura):
    list_display = ["id", "evaluacionid", "genero_baremo", "algoritmo", "creado_en"]
    list_select_related = ["evaluacionid__postulanteid"]
    list_filter = ["genero_baremo", "algoritmo"]


@admin.register(Baremo)
class BaremoAdmin(SoloLectura):
    list_display = ["areaid", "genero", "version", "validado"]
    list_select_related = ["areaid"]
    list_filter = ["genero", "validado"]


@admin.register(PuntoBaremo)
class PuntoAdmin(SoloLectura):
    list_display = ["baremoid", "puntaje_directo", "percentil", "celda_origen"]
    list_select_related = ["baremoid"]
    list_filter = ["baremoid__genero", "baremoid__areaid"]
