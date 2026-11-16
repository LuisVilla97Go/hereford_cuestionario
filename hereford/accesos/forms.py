from django import forms

from .models import ProcesoEvaluacion


class ProcesoAdminForm(forms.ModelForm):
    class Meta:
        model = ProcesoEvaluacion
        fields = [
            "titulo",
            "descripcion",
            "instrucciones",
            "aviso_version",
            "aviso_privacidad",
            "inicio",
            "fin",
            "activo",
            "modalidad",
        ]

    def clean(self):
        datos = super().clean()
        if not self.instance._state.adding:

            modificados = set(self.changed_data)
            actual = ProcesoEvaluacion.objects.select_for_update().get(pk=self.instance.pk)
            for nombre in self.fields:
                if nombre not in modificados and nombre in datos:
                    datos[nombre] = getattr(actual, nombre)

            self.instance = actual
        return datos
