from .exceptions import CatalogoNoDisponible
from .models import AreaVocacional, Baremo, Evaluacion, Postulante, Pregunta, ResultadoArea


def postulantes():
    return Postulante.objects.order_by("creado_en", "pk")


def areas():
    return AreaVocacional.objects.order_by("codigo")


def preguntas():
    return Pregunta.objects.select_related("areaid").order_by("numero")


def evaluaciones():
    return Evaluacion.objects.select_related("postulanteid", "registro_calificacion").order_by(
        "fecha_evaluacion", "pk"
    )


def resultados(evaluacion):
    return (
        ResultadoArea.objects.filter(evaluacionid=evaluacion)
        .select_related("areaid")
        .order_by("areaid__codigo")
    )


def catalogo_calificacion(genero):
    areas_bd = list(areas())
    preguntas_bd = list(preguntas())
    tablas_bd = list(Baremo.objects.filter(genero=genero).prefetch_related("puntos"))
    if (
        genero not in {"M", "F"}
        or len(areas_bd) != 9
        or [p.numero for p in preguntas_bd] != list(range(1, 91))
        or {b.areaid_id for b in tablas_bd} != {a.pk for a in areas_bd}
        or len(tablas_bd) != 9
        or len({b.version for b in tablas_bd}) != 1
    ):
        raise CatalogoNoDisponible()
    por_id = {a.pk: a.codigo for a in areas_bd}
    areas_catalogo = [
        {
            "codigo": a.codigo,
            "nombre": a.nombre,
            "comentario": a.comentario,
            "preguntas": [p.numero for p in preguntas_bd if p.areaid_id == a.pk],
        }
        for a in areas_bd
    ]
    if any(len(a["preguntas"]) != 10 for a in areas_catalogo):
        raise CatalogoNoDisponible()
    baremos = [
        {
            "area": por_id[b.areaid_id],
            "genero": b.genero,
            "version": b.version,
            "regla": b.regla,
            "no_encontrado": b.no_encontrado,
            "validado": b.validado,
            "poblacion_normativa": b.poblacion_normativa,
            "procedencia": b.procedencia,
            "filas": [
                {
                    "puntaje_directo": p.puntaje_directo,
                    "percentil": p.percentil,
                    "celda": p.celda_origen,
                }
                for p in b.puntos.all()
            ],
        }
        for b in sorted(tablas_bd, key=lambda b: por_id[b.areaid_id])
    ]
    if any(not b["filas"] for b in baremos):
        raise CatalogoNoDisponible()
    return {
        "areas": areas_catalogo,
        "preguntas": [
            {"numero": p.numero, "enunciado": p.enunciado, "area": por_id[p.areaid_id]}
            for p in preguntas_bd
        ],
        "baremos": baremos,
    }


def baremos():
    return (
        Baremo.objects.select_related("areaid")
        .prefetch_related("puntos")
        .order_by("areaid__codigo", "genero")
    )
