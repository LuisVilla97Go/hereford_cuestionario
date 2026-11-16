from django.contrib import admin
from django.urls import include, path

from accesos.views import AccesoView

from . import health

urlpatterns = [
    path("acceso", AccesoView.as_view(), name="acceso"),
    path("health/live/", health.live, name="health-live"),
    path("health/ready/", health.ready, name="health-ready"),
    path("admin/", admin.site.urls),
    path("api/", include("hereford.api_urls")),
    path("api-auth/", include("rest_framework.urls")),
]
