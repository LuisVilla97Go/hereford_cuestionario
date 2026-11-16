from rest_framework.exceptions import APIException


class Conflicto(APIException):
    status_code = 409
    default_detail = "La operación no es compatible con el estado actual."
    default_code = "conflicto"


class CatalogoNoDisponible(Conflicto):
    default_detail = (
        "Catálogo o baremo pendiente de revisión. No se guardó la calificación."
    )
    default_code = "catalogo_no_disponible"
