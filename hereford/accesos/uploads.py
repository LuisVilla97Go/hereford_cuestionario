from django.core.files.uploadhandler import FileUploadHandler
from rest_framework.exceptions import ParseError

MAX_BYTES_FOTO = 2 * 1024 * 1024


class LimiteFotoUploadHandler(FileUploadHandler):
    """Corta la recepción antes de almacenar una carga arbitrariamente grande."""

    def __init__(self, request=None):
        super().__init__(request)
        self.recibidos = 0

    def receive_data_chunk(self, raw_data, start):
        self.recibidos += len(raw_data)
        if self.recibidos > MAX_BYTES_FOTO:
            raise ParseError("La foto debe ocupar como máximo 2 MiB.")
        return raw_data

    def file_complete(self, file_size):
        return None
