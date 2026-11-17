from rest_framework import serializers, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from cuestionario import selectors
from cuestionario.models import Baremo, PuntoBaremo
from cuestionario.pagination import PreguntasPagination
from cuestionario.serializers import PreguntaSerializer

from .permissions import GestionaAccesos


class PuntoBaremoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PuntoBaremo
        fields = ["puntaje_directo", "percentil", "celda_origen"]
        read_only_fields = fields


class BaremoSerializer(serializers.ModelSerializer):
    area = serializers.CharField(source="areaid.codigo", read_only=True)
    nombre_area = serializers.CharField(source="areaid.nombre", read_only=True)
    puntos = PuntoBaremoSerializer(many=True, read_only=True)

    class Meta:
        model = Baremo
        fields = [
            "id",
            "area",
            "nombre_area",
            "genero",
            "version",
            "regla",
            "no_encontrado",
            "validado",
            "poblacion_normativa",
            "procedencia",
            "puntos",
        ]
        read_only_fields = fields


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


class BaremoAdminViewSet(viewsets.ReadOnlyModelViewSet):
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
