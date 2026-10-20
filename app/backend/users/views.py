from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers as drf_serializers

from .serializers import (
    UserSerializer,
    UserProfileSerializer,
    UpdateProfileSerializer,
    ChangePasswordSerializer,
    ProfilePhotoSerializer,
)


# Login con límite de intentos por IP para frenar el adivinado de contraseñas
class LoginView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'


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

    @extend_schema(request=None, responses={204: None})
    def delete(self, request):
        usuario = request.user
        usuario.delete()
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
