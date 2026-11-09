from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions
from drf_spectacular.utils import extend_schema_field

Usuario = get_user_model()


class LoginSerializer(serializers.Serializer):
    """Datos del login con sesión."""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class UserSerializer(serializers.ModelSerializer):
    # Evito que se devuelva en el JSON de respuesta
    password = serializers.CharField(write_only=True)

    class Meta:
        model = Usuario
        fields = ("id", "email", "password", "nombre", "apellidos", "foto_perfil")

    def validate_password(self, valor):
        try:
            validate_password(valor)
        except exceptions.ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return valor

    def create(self, validated_data):
        usuario = Usuario.objects.create_user(**validated_data)
        return usuario


class UserProfileSerializer(serializers.ModelSerializer):
    """Devuelve el perfil del usuario autenticado, con la URL de la foto."""
    foto_perfil_url = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = ("id", "email", "nombre", "apellidos", "foto_perfil_url", "tema")

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_foto_perfil_url(self, obj):
        if not obj.foto_perfil:
            return None
        try:
            # GarageStorage.url() genera la URL presignada con el endpoint público.
            return obj.foto_perfil.url
        except Exception:
            return None


class UpdateProfileSerializer(serializers.ModelSerializer):
    """Permite actualizar nombre, apellidos, email y/o tema del usuario."""

    class Meta:
        model = Usuario
        fields = ("nombre", "apellidos", "email", "tema")
        extra_kwargs = {
            "nombre":    {"required": False},
            "apellidos": {"required": False},
            "email":     {"required": False},
            "tema":      {"required": False},
        }

    def validate_email(self, valor):
        usuario = self.context["request"].user
        if Usuario.objects.exclude(pk=usuario.pk).filter(email=valor).exists():
            raise serializers.ValidationError("Este email ya está en uso.")
        return valor


class ChangePasswordSerializer(serializers.Serializer):
    """Valida y cambia la contraseña del usuario."""
    password_actual = serializers.CharField(write_only=True)
    password_nuevo  = serializers.CharField(write_only=True)

    def validate_password_actual(self, valor):
        usuario = self.context["request"].user
        if not usuario.check_password(valor):
            raise serializers.ValidationError("La contraseña actual no es correcta.")
        return valor

    def validate_password_nuevo(self, valor):
        try:
            validate_password(valor)
        except exceptions.ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return valor


class ProfilePhotoSerializer(serializers.ModelSerializer):
    """Recibe y guarda la foto de perfil."""

    class Meta:
        model = Usuario
        fields = ("foto_perfil",)

    def validate_foto_perfil(self, valor):
        tamano_maximo_mb = 10
        if valor.size > tamano_maximo_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"La imagen no puede superar {tamano_maximo_mb} MB."
            )
        tipos_permitidos = ["image/jpeg", "image/png", "image/webp", "image/gif"]
        if valor.content_type not in tipos_permitidos:
            raise serializers.ValidationError(
                "Formato no permitido. Usa JPG, PNG, WEBP o GIF."
            )
        return valor
