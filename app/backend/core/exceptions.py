import re

from botocore.exceptions import BotoCoreError
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_standardized_errors.handler import ExceptionHandler
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.serializers import as_serializer_error

from items.services import BorradoGarageFallido

# Formato exacto de $request_id de Nginx; cualquier otra cosa se ignora (evita escribir líneas falsas en el log)
_FORMATO_REQUEST_ID = re.compile(r'[0-9a-f]{32}')


class AlmacenamientoNoDisponible(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = 'El almacenamiento no responde. Inténtalo de nuevo.'
    default_code = 'almacenamiento_no_disponible'


class ManejadorErrores(ExceptionHandler):
    """Traduce los errores previstos de los servicios; el resto acaba en un 500 genérico y en el log."""

    def convert_known_exceptions(self, exc):
        if isinstance(exc, DjangoValidationError):
            return ValidationError(as_serializer_error(exc))
        if isinstance(exc, (BotoCoreError, BorradoGarageFallido)):
            return AlmacenamientoNoDisponible()
        return super().convert_known_exceptions(exc)

    def convert_unhandled_exceptions(self, exc):
        # El 500 genérico con el texto de DRF, ya traducido al idioma de LANGUAGE_CODE
        exc = exc if isinstance(exc, APIException) else APIException()
        ref = self.context['request'].META.get('HTTP_X_REQUEST_ID', '')
        # En los 5xx, la misma referencia sale en la respuesta y en la línea del log
        if status.is_server_error(exc.status_code) and _FORMATO_REQUEST_ID.fullmatch(ref):
            exc = type(exc)(detail=f'{exc.detail} (ref. {ref})', code=exc.detail.code)
        return exc
