import logging

from django.core.cache import caches
from redis.exceptions import RedisError

from .models import Pregunta

logger = logging.getLogger(__name__)
CLAVE = "preguntas-participante-v1"
TTL = 60


def preguntas_participante():
    cache = caches["catalogo"]
    disponible = True
    try:
        datos = cache.get(CLAVE)
    except RedisError, OSError:
        logger.warning("Caché del catálogo no disponible; se consulta PostgreSQL.")
        datos = None
        disponible = False
    if datos is None:
        datos = list(Pregunta.objects.order_by("numero").values("numero", "enunciado"))
        if disponible:
            try:
                cache.set(CLAVE, datos, timeout=TTL)
            except RedisError, OSError:
                logger.warning("No se pudo guardar la caché del catálogo.")
    return datos
