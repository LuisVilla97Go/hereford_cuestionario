from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accesos.models import AsignacionEvaluacion, IdentidadAcceso

from . import selectors, services
from .exceptions import Conflicto
from .models import RegistroCalificacion
from .pagination import PreguntasPagination
from .permissions import PersonalConPermisos
from .serializers import (
    AreaVocacionalSerializer,
    EnviarRespuestasSerializer,
    EvaluacionSerializer,
    PostulanteSerializer,
    PreguntaSerializer,
    ResultadoAreaSerializer,
)


def _comprobar_no_vinculado(postulante):
    if IdentidadAcceso.objects.filter(postulanteid=postulante).exists():
        raise Conflicto("La ficha vinculada a una cuenta requiere un flujo de corrección auditado.")


class PostulanteViewSet(viewsets.ModelViewSet):
    permission_classes = [PersonalConPermisos]
    serializer_class = PostulanteSerializer
    queryset = selectors.postulantes()

    def perform_update(self, serializer):
        _comprobar_no_vinculado(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        _comprobar_no_vinculado(instance)
        instance.delete()


class AreaVocacionalViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [PersonalConPermisos]
    serializer_class = AreaVocacionalSerializer
    queryset = selectors.areas()


class PreguntaViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [PersonalConPermisos]
    serializer_class = PreguntaSerializer
    pagination_class = PreguntasPagination
    queryset = selectors.preguntas()


class EvaluacionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [PersonalConPermisos]
    permisos_por_accion = {
        "respuestas": ["cuestionario.add_respuesta"],
        "resultados": ["cuestionario.view_resultadoarea"],
    }
    serializer_class = EvaluacionSerializer
    queryset = selectors.evaluaciones()

    def perform_create(self, serializer):
        _comprobar_no_vinculado(serializer.validated_data["postulanteid"])
        serializer.save()

    @action(detail=True, methods=["post"])
    def respuestas(self, request, pk=None, format=None):
        evaluacion = self.get_object()
        if AsignacionEvaluacion.objects.filter(evaluacionid=evaluacion).exists():
            raise Conflicto("La evaluación pertenece a una asignación; responde el participante.")
        if evaluacion.completado:
            raise Conflicto("Esta evaluación ya está completada.")
        serializer = EnviarRespuestasSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        evaluacion = services.registrar_respuestas(
            evaluacion, serializer.validated_data["respuestas"]
        )
        return Response(EvaluacionSerializer(evaluacion).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def resultados(self, request, pk=None, format=None):
        evaluacion = self.get_object()
        if not evaluacion.completado:
            raise Conflicto("La evaluación todavía no está completada.")
        try:
            registro = evaluacion.registro_calificacion
        except RegistroCalificacion.DoesNotExist:
            registro = None
        snapshot = registro.snapshot if registro else {}
        return Response(
            {
                "evaluacion": str(evaluacion.pk),
                "reportable": False,
                "estado_conversion": snapshot.get(
                    "estado_conversion", "completa" if registro else "no_disponible"
                ),
                "areas_pendientes": snapshot.get("areas_pendientes", []),
                "limitacion": snapshot.get(
                    "limitacion",
                    "Conversión técnica interna. Población normativa y edición no acreditadas.",
                ),
                "catalogo_sha256": registro.catalogo_sha256 if registro else None,
                "genero_baremo": registro.genero_baremo if registro else None,
                "algoritmo": registro.algoritmo if registro else None,
                "resultados": ResultadoAreaSerializer(
                    selectors.resultados(evaluacion),
                    many=True,
                    context={
                        "conversiones": snapshot.get("conversiones", {}),
                        "nombres_area": {
                            area["codigo"]: area["nombre"]
                            for area in snapshot.get("catalogo", {}).get("areas", [])
                        },
                    },
                ).data,
            }
        )
