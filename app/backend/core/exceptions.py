from botocore.exceptions import BotoCoreError
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_standardized_errors.handler import ExceptionHandler
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.serializers import as_serializer_error

from items.services import BorradoGarageFallido


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
