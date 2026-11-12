import logging

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers as drf_serializers

from items.services import BorradoGarageFallido, ItemService

from .serializers import (
    LoginSerializer,
    UserSerializer,
    UserProfileSerializer,
    UpdateProfileSerializer,
    ChangePasswordSerializer,
    ProfilePhotoSerializer,
)

logger = logging.getLogger(__name__)


# Entrega la cookie csrftoken
@method_decorator(ensure_csrf_cookie, name='dispatch')
class CsrfView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None})
    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


# Login con sesión y límite de intentos por IP.
# csrf_protect porque DRF no comprueba CSRF sin sesión iniciada (login CSRF).
@method_decorator(csrf_protect, name='dispatch')
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    @extend_schema(request=LoginSerializer, responses=UserProfileSerializer)
    def post(self, request):
        serializador = LoginSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        usuario = authenticate(
            request,
            email=serializador.validated_data['email'],
            password=serializador.validated_data['password'],
        )
        if usuario is None:
            raise AuthenticationFailed('Email o contraseña incorrectos.')
        login(request, usuario)
        return Response(UserProfileSerializer(usuario, context={"request": request}).data)


# AllowAny: cerrar una sesión ya caducada no da error
class LogoutView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    post=extend_schema(request=UserSerializer, responses={201: UserSerializer}),
)
# Registro de nuevos usuarios
class RegisterView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'registro'


# GET: perfil del usuario. PATCH: actualiza nombre/apellidos/email. DELETE: elimina cuenta.
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserProfileSerializer)
    def get(self, request):
        serializador = UserProfileSerializer(request.user, context={"request": request})
        return Response(serializador.data)

    @extend_schema(request=UpdateProfileSerializer, responses=UserProfileSerializer)
    def patch(self, request):
        serializador = UpdateProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializador.is_valid(raise_exception=True)
        serializador.save()
        return Response(UserProfileSerializer(request.user, context={"request": request}).data)

    @extend_schema(request=None, responses={204: None, 503: None})
    def delete(self, request):
        usuario = request.user
        # Garage primero: si falla, la cuenta sigue entera y se puede reintentar
        claves = ItemService.claves_del_usuario(usuario)
        if usuario.foto_perfil:
            claves.append(usuario.foto_perfil.name)
        try:
            ItemService.delete_s3_keys(claves, settings.AWS_STORAGE_BUCKET_NAME)
        except (BorradoGarageFallido, BotoCoreError, ClientError):
            logger.exception("No se pudieron borrar de Garage los ficheros del usuario %s", usuario.pk)
            return Response(
                {"detail": "No se pudo borrar la cuenta. Inténtalo de nuevo."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        # Elasticsearch se limpia solo con las señales de django-elasticsearch-dsl
        usuario.delete()
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# Cambia la contraseña del usuario autenticado
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'cambiar_password'

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={200: inline_serializer('ChangePasswordResponse', fields={'detail': drf_serializers.CharField()})},
    )
    def post(self, request):
        serializador = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializador.is_valid(raise_exception=True)
        request.user.set_password(serializador.validated_data["password_nuevo"])
        request.user.save()
        # Mantiene la sesión actual; las demás se cierran
        update_session_auth_hash(request, request.user)
        return Response({"detail": "Contraseña actualizada correctamente."})


# Sube o reemplaza la foto de perfil (guardada en Garage/S3)
class ProfilePhotoView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ProfilePhotoSerializer,
        responses={200: inline_serializer('ProfilePhotoResponse', fields={'foto_perfil_url': drf_serializers.URLField(allow_null=True)})},
    )
    def post(self, request):
        usuario = request.user

        # Eliminar la foto anterior de S3 si existe
        if usuario.foto_perfil:
            try:
                usuario.foto_perfil.delete(save=False)
            except Exception:
                pass

        serializador = ProfilePhotoSerializer(usuario, data=request.data, partial=True)
        serializador.is_valid(raise_exception=True)
        serializador.save()

        url_foto = None
        if usuario.foto_perfil:
            try:
                url_foto = usuario.foto_perfil.url
            except Exception:
                pass

        return Response({"foto_perfil_url": url_foto}, status=status.HTTP_200_OK)
