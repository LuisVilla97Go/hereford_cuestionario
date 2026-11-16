import logging
import warnings
from io import BytesIO
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import (
    APIException,
    NotFound,
    PermissionDenied,
    ValidationError,
)

from .models import FotoParticipante, IdentidadAcceso
from .uploads import MAX_BYTES_FOTO

logger = logging.getLogger(__name__)
MAX_PIXELES = 4_000_000
URL_SEGUNDOS = 300


class AlmacenamientoNoDisponible(APIException):
    status_code = 503
    default_detail = "El almacenamiento de fotos no está disponible. Intente más tarde."
    default_code = "almacenamiento_no_disponible"


def cliente_s3(region):
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "virtual"},
            connect_timeout=3,
            read_timeout=5,
            retries={"total_max_attempts": 1},
        ),
    )


def normalizar_foto(archivo):
    contenido = archivo.read(MAX_BYTES_FOTO + 1)
    if not contenido or len(contenido) > MAX_BYTES_FOTO:
        raise ValidationError({"foto": "La imagen debe ocupar como máximo 2 MiB."})
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(contenido), formats=["JPEG", "PNG"]) as original:
                if (
                    original.width * original.height > MAX_PIXELES
                    or getattr(original, "n_frames", 1) != 1
                ):
                    raise ValidationError({"foto": "Máximo 4 megapíxeles y una sola imagen."})
                original.load()
                orientada = ImageOps.exif_transpose(original).convert("RGB")
                orientada.thumbnail((1200, 1200))
                limpia = Image.new("RGB", orientada.size)
                limpia.paste(orientada)
                salida = BytesIO()
                limpia.save(salida, format="JPEG", quality=85, optimize=True)
                return salida.getvalue(), limpia.width, limpia.height
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValidationError({"foto": "Se requiere una imagen JPEG o PNG válida."}) from exc


def _eliminar_huerfana(bucket, region, clave):
    try:
        cliente_s3(region).delete_object(Bucket=bucket, Key=clave)
    except BotoCoreError, ClientError:
        logger.error(
            "No se pudo limpiar una foto anterior; requiere conciliación de almacenamiento."
        )


def guardar_foto(user, archivo):
    datos, ancho, alto = normalizar_foto(archivo)
    bucket, region = settings.AWS_S3_BUCKET, settings.AWS_S3_REGION
    if not bucket:
        raise AlmacenamientoNoDisponible()
    clave = f"fotos/{uuid4().hex}.jpg"
    subida = False
    try:
        with transaction.atomic():
            identidad = (
                IdentidadAcceso.objects.select_for_update()
                .select_related("usuarioid")
                .get(usuarioid=user)
            )
            if not identidad.acceso_confirmado or not identidad.usuarioid.is_active:
                raise PermissionDenied()
            anterior = FotoParticipante.objects.filter(identidadid=identidad).first()
            cliente_s3(region).put_object(
                Bucket=bucket,
                Key=clave,
                Body=datos,
                ContentType="image/jpeg",
                ServerSideEncryption="AES256",
                CacheControl="private, no-store",
            )
            subida = True
            foto, _ = FotoParticipante.objects.update_or_create(
                identidadid=identidad,
                defaults={
                    "bucket": bucket,
                    "region": region,
                    "clave": clave,
                    "tamano": len(datos),
                    "ancho": ancho,
                    "alto": alto,
                    "aceptada_en": timezone.now(),
                },
            )
            if anterior:
                transaction.on_commit(
                    lambda: _eliminar_huerfana(anterior.bucket, anterior.region, anterior.clave)
                )
        return foto
    except (BotoCoreError, ClientError) as exc:
        if subida:
            _eliminar_huerfana(bucket, region, clave)
        raise AlmacenamientoNoDisponible() from exc
    except Exception:
        if subida:
            _eliminar_huerfana(bucket, region, clave)
        raise


def foto_propia(user):
    try:
        return FotoParticipante.objects.get(identidadid__usuarioid=user)
    except FotoParticipante.DoesNotExist as exc:
        raise NotFound("No tiene una foto registrada.") from exc


def datos_foto(foto):
    try:
        url = cliente_s3(foto.region).generate_presigned_url(
            "get_object",
            Params={
                "Bucket": foto.bucket,
                "Key": foto.clave,
                "ResponseContentType": "image/jpeg",
                "ResponseContentDisposition": 'inline; filename="foto.jpg"',
            },
            ExpiresIn=URL_SEGUNDOS,
        )
    except (BotoCoreError, ClientError) as exc:
        raise AlmacenamientoNoDisponible() from exc
    return {
        "url": url,
        "vence_en_segundos": URL_SEGUNDOS,
        "ancho": foto.ancho,
        "alto": foto.alto,
    }


@transaction.atomic
def eliminar_foto(user):
    identidad = IdentidadAcceso.objects.select_for_update().get(usuarioid=user)
    foto = FotoParticipante.objects.filter(identidadid=identidad).first()
    if foto is None:
        return
    try:
        cliente_s3(foto.region).delete_object(Bucket=foto.bucket, Key=foto.clave)
    except (BotoCoreError, ClientError) as exc:
        raise AlmacenamientoNoDisponible() from exc
    foto.delete()
