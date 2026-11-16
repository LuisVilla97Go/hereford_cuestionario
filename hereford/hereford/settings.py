import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
from redis.backoff import NoBackoff
from redis.retry import Retry

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent


def required_env(name):
    value = os.environ.get(name)
    if not value or not value.strip():
        raise ImproperlyConfigured(f"Falta la variable {name}.")
    return value


SECRET_KEY = required_env("DJANGO_SECRET_KEY")

debug_value = os.environ.get("DJANGO_DEBUG", "false").lower()
if debug_value not in {"true", "false"}:
    raise ImproperlyConfigured("DJANGO_DEBUG debe ser true o false.")
DEBUG = debug_value == "true"

ALLOWED_HOSTS = [
    host.strip() for host in required_env("DJANGO_ALLOWED_HOSTS").split(",") if host.strip()
]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "cuestionario",
    "accesos",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "accesos.middleware.ApiNoStoreMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "hereford.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "hereford.wsgi.application"
ASGI_APPLICATION = "hereford.asgi.application"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAdminUser"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 100,
}

redis_url = os.environ.get("REDIS_URL")
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "catalogo": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    },
}
if redis_url:
    CACHES["catalogo"] = {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": redis_url,
        "KEY_PREFIX": "hereford-catalogo",
        "OPTIONS": {
            "socket_connect_timeout": 1,
            "socket_timeout": 1,
            "retry": Retry(NoBackoff(), 0),
        },
    }

AUTHENTICATION_BACKENDS = [
    "accesos.backends.CorreoBackend",
    "django.contrib.auth.backends.ModelBackend",
]
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "CHECK_REVOKE_TOKEN": True,
}


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": required_env("DATABASE_NAME"),
        "USER": required_env("DATABASE_USER"),
        "PASSWORD": required_env("DATABASE_PASSWORD"),
        "HOST": required_env("DATABASE_HOST"),
        "PORT": required_env("DATABASE_PORT"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 5},
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "es-pe"

TIME_ZONE = "America/Lima"

USE_I18N = True

USE_TZ = True


STATIC_URL = "static/"


MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.dummy.EmailBackend",
    },
}
ACCESOS_ENVIOS_HABILITADOS = False
ACCESOS_URL_PUBLICA = "http://localhost:8000"
ACCESOS_PROXY_CONFIABLE = False
DEFAULT_FROM_EMAIL = "orientacion@example.invalid"

AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET", "")
AWS_S3_REGION = os.environ.get("AWS_S3_REGION", "us-east-2")
