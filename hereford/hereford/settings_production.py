import os
from django.core.exceptions import ImproperlyConfigured
from .settings_container import *
from .settings_container import ALLOWED_HOSTS, DEBUG, SECRET_KEY

if DEBUG:
    raise ImproperlyConfigured("Producción exige DJANGO_DEBUG=false.")
if (
    len(SECRET_KEY) < 50
    or len(set(SECRET_KEY)) < 5
    or SECRET_KEY.startswith("ejemplo-")
):
    raise ImproperlyConfigured(
        "Producción exige una DJANGO_SECRET_KEY aleatoria y robusta."
    )
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Producción exige hosts explícitos.")
if not os.environ.get("REDIS_URL"):
    raise ImproperlyConfigured("Producción exige REDIS_URL para la caché del catálogo.")

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": os.environ.get("SMTP_HOST") or "localhost",
            "port": 587,
            "username": os.environ.get("SMTP_USERNAME", ""),
            "password": os.environ.get("SMTP_PASSWORD", ""),
            "use_tls": True,
            "timeout": 5,
        },
    },
}

SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/(live|ready)/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS]
ACCESOS_URL_PUBLICA = CSRF_TRUSTED_ORIGINS[0]
proxy = os.environ.get("DJANGO_TRUST_PROXY", "false").lower()
if proxy not in {"true", "false"}:
    raise ImproperlyConfigured("DJANGO_TRUST_PROXY debe ser true o false.")
if proxy == "true":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    ACCESOS_PROXY_CONFIABLE = True
    ACCESOS_PROXY_RENDER = (
        os.environ.get("RENDER") == "true"
        and os.environ.get("RENDER_SERVICE_TYPE") == "web"
    )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
