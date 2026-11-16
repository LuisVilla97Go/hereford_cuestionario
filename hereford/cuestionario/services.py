from django.db import transaction
from django.db.models import Count, Max, Min, Sum
from rest_framework.exceptions import ValidationError

from .calificacion import calificar_puntajes
from .exceptions import CatalogoNoDisponible, Conflicto
from .models import (
    Evaluacion,
    Postulante,
    RegistroCalificacion,
    Respuesta,
    ResultadoArea,
)
from .selectors import catalogo_calificacion
from .serializers import EnviarRespuestasSerializer


@transaction.atomic
def registrar_respuestas(evaluacion, items):
    locked = Evaluacion.objects.select_for_update().get(pk=evaluacion.pk)
    if locked.completado:
        raise Conflicto("Esta evaluación ya está completada.")
    validator = EnviarRespuestasSerializer(data={"respuestas": items})
    validator.is_valid(raise_exception=True)
    if locked.respuestas.exists() or locked.resultados.exists():
        raise Conflicto("La evaluación tiene datos parciales y requiere revisión.")
    Respuesta.objects.bulk_create(
        [
            Respuesta(evaluacionid=locked, preguntaid_id=item["pregunta"], valor=item["valor"])
            for item in validator.validated_data["respuestas"]
        ]
    )
    return calificar(locked)


@transaction.atomic
def calificar(evaluacion):
    locked = Evaluacion.objects.select_for_update().get(pk=evaluacion.pk)
    if locked.completado:
        raise Conflicto("Esta evaluación ya está completada.")
    postulante = Postulante.objects.select_for_update().get(pk=locked.postulanteid_id)
    catalogo = catalogo_calificacion(postulante.genero)
    sumas = list(
        Respuesta.objects.filter(evaluacionid=locked)
        .values("preguntaid__areaid_id", "preguntaid__areaid__codigo")
        .annotate(
            puntaje=Sum("valor"),
            cantidad=Count("pk"),
            minimo=Min("valor"),
            maximo=Max("valor"),
        )
        .order_by("preguntaid__areaid__codigo")
    )
    if len(sumas) != 9 or any(
        s["cantidad"] != 10 or s["minimo"] < 1 or s["maximo"] > 5 for s in sumas
    ):
        raise ValidationError(
            "Se requieren diez respuestas válidas por cada una de las nueve áreas."
        )
    puntos = {s["preguntaid__areaid__codigo"]: s["puntaje"] for s in sumas}
    try:
        calculo = calificar_puntajes(puntos, postulante.genero, catalogo)
    except ValueError as exc:
        raise CatalogoNoDisponible() from exc
    area_ids = {s["preguntaid__areaid__codigo"]: s["preguntaid__areaid_id"] for s in sumas}
    ResultadoArea.objects.bulk_create(
        [
            ResultadoArea(
                evaluacionid=locked,
                areaid_id=area_ids[item["area"]],
                puntaje_directo=item["puntaje_directo"],
                percentil=item["percentil"],
                interpretacion=item["interpretacion"],
            )
            for item in calculo["resultados"]
        ]
    )
    RegistroCalificacion.objects.create(
        evaluacionid=locked,
        catalogo_sha256=calculo["catalogo_sha256"],
        genero_baremo=calculo["genero_baremo"],
        algoritmo=calculo["algoritmo"],
        snapshot={
            "catalogo": catalogo,
            "reportable": calculo["reportable"],
            "estado_conversion": calculo["estado_conversion"],
            "areas_pendientes": calculo["areas_pendientes"],
            "limitacion": calculo["limitacion"],
            "conversiones": {
                item["area"]: {
                    "puntaje_baremo": item["puntaje_baremo"],
                    "tipo_coincidencia": item["tipo_coincidencia"],
                    "estado_conversion": item["estado_conversion"],
                    "motivo_pendiente": item["motivo_pendiente"],
                }
                for item in calculo["resultados"]
            },
        },
    )
    locked.completado = True
    locked.save(update_fields=["completado"])
    return locked
