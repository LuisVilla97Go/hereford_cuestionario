from math import isfinite
from statistics import variance


def alfa_cronbach(matriz):
    if len(matriz) < 2 or len(matriz[0]) < 2:
        raise ValueError("Se requieren al menos dos personas y dos ítems.")
    k = len(matriz[0])
    if any(len(row) != k for row in matriz):
        raise ValueError("Matriz no rectangular.")
    if any(
        type(v) not in (int, float) or not isfinite(v) for row in matriz for v in row
    ):
        raise ValueError("Hay valores ausentes o no numéricos finitos.")
    total_var = variance([sum(row) for row in matriz])
    if total_var == 0:
        raise ValueError("Varianza total cero: alfa no definido.")
    return (
        k
        / (k - 1)
        * (1 - sum(variance(col) for col in zip(*matriz, strict=True)) / total_var)
    )


SIGUIENTE_MAYOR = "exacto_o_siguiente_mayor"
MAS_CERCANO = "mas_cercano_empate_inferior"
REGLAS = (SIGUIENTE_MAYOR, MAS_CERCANO)


def _resultado(fila, tipo):
    return {
        "percentil": fila["percentil"],
        "puntaje_baremo": fila["puntaje_directo"],
        "tipo_coincidencia": tipo,
    }


def conversion_por_tabla(puntaje, filas, *, regla=SIGUIENTE_MAYOR, no_encontrado=99):

    if type(puntaje) is not int or not 10 <= puntaje <= 50:
        raise ValueError("Puntaje directo fuera de 10–50.")
    if regla not in REGLAS or not filas:
        raise ValueError("Regla desconocida o tabla vacía.")
    if any(
        type(f["puntaje_directo"]) is not int
        or not 10 <= f["puntaje_directo"] <= 50
        or type(f["percentil"]) is not int
        or not 1 <= f["percentil"] <= 99
        for f in filas
    ):
        raise ValueError("Tabla fuera de rango.")
    if any(
        a["puntaje_directo"] <= b["puntaje_directo"] or a["percentil"] <= b["percentil"]
        for a, b in zip(filas, filas[1:], strict=False)
    ):
        raise ValueError("Baremo no monótono o ambiguo: pendiente de revisión.")
    exacta = next((f for f in filas if f["puntaje_directo"] == puntaje), None)
    if exacta is not None:
        return _resultado(exacta, "exacta")
    mayores = [f for f in filas if f["puntaje_directo"] > puntaje]
    menores = [f for f in filas if f["puntaje_directo"] < puntaje]
    superior = min(mayores, key=lambda f: f["puntaje_directo"]) if mayores else None
    inferior = max(menores, key=lambda f: f["puntaje_directo"]) if menores else None
    if regla == SIGUIENTE_MAYOR:
        if superior is None:
            return {
                "percentil": no_encontrado,
                "puntaje_baremo": None,
                "tipo_coincidencia": "supera_umbral_maximo",
            }
        return _resultado(superior, "siguiente_mayor")
    if superior is None:
        return _resultado(inferior, "supera_umbral_maximo")
    if inferior is None:
        return _resultado(superior, "bajo_umbral_minimo")
    hasta_inferior = puntaje - inferior["puntaje_directo"]
    hasta_superior = superior["puntaje_directo"] - puntaje
    if hasta_inferior < hasta_superior:
        return _resultado(inferior, "mas_cercano_inferior")
    if hasta_superior < hasta_inferior:
        return _resultado(superior, "mas_cercano_superior")
    return _resultado(inferior, "empate_inferior")


def percentil_por_tabla(puntaje, filas, *, regla=SIGUIENTE_MAYOR, no_encontrado=99):
    return conversion_por_tabla(
        puntaje, filas, regla=regla, no_encontrado=no_encontrado
    )["percentil"]
