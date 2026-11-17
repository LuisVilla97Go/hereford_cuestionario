from rest_framework import mixins, serializers, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from cuestionario import selectors
from cuestionario.models import Baremo
from cuestionario.pagination import PreguntasPagination
from cuestionario.psicometria import conversion_por_tabla
from cuestionario.serializers import PreguntaSerializer

from .permissions import GestionaAccesos


class BaremoSerializer(serializers.ModelSerializer):
    area = serializers.CharField(source="areaid.codigo", read_only=True)
    nombre_area = serializers.CharField(source="areaid.nombre", read_only=True)
    tabla = serializers.SerializerMethodField()

    class Meta:
        model = Baremo
        fields = ["area", "nombre_area", "genero", "tabla"]
        read_only_fields = fields

    def get_tabla(self, baremo):
        filas = [
            {"puntaje_directo": p.puntaje_directo, "percentil": p.percentil}
            for p in baremo.puntos.all()
        ]

        def percentil(puntaje):
            if not baremo.validado:
                return None
            try:
                return conversion_por_tabla(
                    puntaje, filas, regla=baremo.regla, no_encontrado=baremo.no_encontrado
                )["percentil"]
            except ValueError:
                return None

        return [{"puntaje": n, "percentil": percentil(n)} for n in range(10, 51)]


class PreguntaAdminViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [GestionaAccesos]
    serializer_class = PreguntaSerializer
    pagination_class = PreguntasPagination

    def get_queryset(self):
        consulta = selectors.preguntas()
        if area := self.request.query_params.get("area"):
            consulta = consulta.filter(areaid__codigo=area)
        return consulta


class BaremoAdminViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [GestionaAccesos]
    serializer_class = BaremoSerializer

    def get_queryset(self):
        consulta = selectors.baremos()
        if area := self.request.query_params.get("area"):
            consulta = consulta.filter(areaid__codigo=area)
        if genero := self.request.query_params.get("genero"):
            consulta = consulta.filter(genero=genero)
        return consulta
