from .settings import *
from .settings import BASE_DIR, MIDDLEWARE

MIDDLEWARE = [
    MIDDLEWARE[0],
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[1:],
]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_URL = "/static/"
ACCESOS_URL_PUBLICA = "http://127.0.0.1:8023"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
