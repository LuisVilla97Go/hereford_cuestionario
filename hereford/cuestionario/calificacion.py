import hashlib
import json

from .psicometria import REGLAS, conversion_por_tabla

ALGORITMO = "hereford-suma-area-baremo-v4"


def version_catalogo(catalogo):
    data = json.dumps(catalogo, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def calificar_puntajes(puntos, genero, catalogo):
    if genero not in {"M", "F"}:
        raise ValueError("Grupo de baremación desconocido.")
    if set(puntos) != {a["codigo"] for a in catalogo["areas"]} or any(
        type(p) is not int or not 10 <= p <= 50 for p in puntos.values()
    ):
        raise ValueError("Puntajes por área incompletos o inválidos.")
    tablas = {(b["area"], b["genero"]): b for b in catalogo["baremos"]}
    resultados = []
    for area in catalogo["areas"]:
        tabla = tablas.get((area["codigo"], genero))
        if tabla is None or not tabla["filas"] or tabla["regla"] not in REGLAS:
            raise ValueError("Baremo ausente o regla desconocida.")
        if not tabla["validado"]:
            conversion = {
                "percentil": None,
                "puntaje_baremo": None,
                "tipo_coincidencia": "pendiente_revision",
                "estado_conversion": "pendiente_baremo",
                "motivo_pendiente": "El baremo de esta área y grupo requiere revisión.",
            }
        else:
            conversion = {
                **conversion_por_tabla(
                    puntos[area["codigo"]],
                    tabla["filas"],
                    regla=tabla["regla"],
                    no_encontrado=tabla["no_encontrado"],
                ),
                "estado_conversion": "convertido",
                "motivo_pendiente": None,
            }
        resultados.append(
            {
                "area": area["codigo"],
                "puntaje_directo": puntos[area["codigo"]],
                **conversion,
                "interpretacion": area["comentario"],
            }
        )
    pendientes = [r["area"] for r in resultados if r["estado_conversion"] == "pendiente_baremo"]
    return {
        "resultados": resultados,
        "genero_baremo": genero,
        "catalogo_sha256": version_catalogo(catalogo),
        "algoritmo": ALGORITMO,
        "reportable": False,
        "estado_conversion": "parcial" if pendientes else "completa",
        "areas_pendientes": pendientes,
        "limitacion": ("Hay conversiones pendientes de revisión. " if pendientes else "")
        + "Población normativa y edición no acreditadas.",
    }
