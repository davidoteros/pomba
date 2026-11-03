from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from .models import Item, ItemVersion
from .services import (
    ItemService,
    mime_previsualizable,
    mime_con_preview_generada,
    tipo_visor,
    PREVIEW_FALLIDA,
)


class ItemSerializer(serializers.ModelSerializer):
    tiene_hijos = serializers.BooleanField(read_only=True)
    file = serializers.FileField(allow_empty_file=True, required=False, allow_null=True)
    # Fuente de verdad para saver si algo se puede previsualizar o no (Queremos evitar inyecciones)
    previsualizable = serializers.SerializerMethodField()
    # Con qué visor lo muestra el frontend: 'imagen', 'audio', 'video' o 'pdf'.
    tipo_visor = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            "id",
            "nombre",
            "tipo",
            "padre",
            "usuario",
            "file",
            "tamano_bytes",
            "mime_type",
            "previsualizable",
            "tipo_visor",
            "metadatos",
            "favorito",
            "eliminado",
            "fecha_eliminado",
            "fecha_creacion",
            "fecha_modificacion",
            "tiene_hijos",
        ]
        read_only_fields = [
            "id",
            "usuario",
            "tamano_bytes",
            "mime_type",
            "eliminado",
            "fecha_eliminado",
            "fecha_creacion",
            "fecha_modificacion",
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_previsualizable(self, obj):
        if obj.tipo != Item.Tipo.ARCHIVO:
            return False
        if mime_previsualizable(obj.mime_type) is not None:
            return True
        return (
            mime_con_preview_generada(obj.mime_type)
            and bool(obj.preview_key)
            and obj.preview_key != PREVIEW_FALLIDA
        )

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_tipo_visor(self, obj):
        if not self.get_previsualizable(obj):
            return None
        return tipo_visor(obj.mime_type)

    # Hacemos una validación basica (Esto solo se llama cuando se hace post, put o patch)
    def validate_padre(self, value):

        #Si no tiene padre, es correcto ya que es la raiz
        if value is None:
            return value
        #Comprobamos que la carpeta sea del usuario que hace la petición
        if value.usuario_id != self.context['request'].user.id:
            raise serializers.ValidationError("Carpeta no encontrada")
        #Comprobamos que el padre seas una carpeta
        if value.tipo != Item.Tipo.CARPETA:
            raise serializers.ValidationError("Debe ser carpeta")
        #Comprobamos que no este creando sobre la papelera
        if value.eliminado:
            raise serializers.ValidationError("No puedes usar una carpeta en papelera")

        return value


class ItemVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ItemVersion
        fields = ['id', 'numero', 'tamano_bytes', 'mime_type', 'metadatos', 'es_actual', 'fecha_creacion']


# =========================================================
# SUBIDA PRESIGNADA
# =========================================================
# El tamaño es obligatorio al pedir el pase: la cuota se cobra antes de firmar la  URL, porque el PUT va del navegador a Garage sin pasar por Django.

class SolicitarSubidaSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=255, trim_whitespace=True)
    tamano_bytes = serializers.IntegerField(min_value=0)
    mime_type = serializers.CharField(max_length=100, required=False, default='application/octet-stream')


class ConfirmarSubidaSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=255, trim_whitespace=True)
    key = serializers.CharField(max_length=500, trim_whitespace=True)
    padre = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.all(), required=False, allow_null=True, default=None,
    )
    mime_type = serializers.CharField(max_length=100, required=False, default='application/octet-stream')

    def validate_padre(self, value):
        """La carpeta destino tiene que ser del usuario, ser carpeta y no estar en papelera."""
        if value is None:
            return value
        usuario = self.context['request'].user
        if value.usuario_id != usuario.id or value.tipo != Item.Tipo.CARPETA or value.eliminado:
            raise serializers.ValidationError("Carpeta padre no encontrada.")
        return value


class VersionSolicitarSubidaSerializer(serializers.Serializer):
    tamano_bytes = serializers.IntegerField(min_value=0)


class VersionConfirmarSubidaSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=500, trim_whitespace=True)
    mime_type = serializers.CharField(max_length=100)

    def validate_mime_type(self, value):
        """Las versiones son solo de audio: no permitimos convertir un audio en HTML/SVG al confirmar."""
        if not value.split(';')[0].strip().lower().startswith('audio/'):
            raise serializers.ValidationError("El control de versiones solo acepta archivos de audio.")
        return value
