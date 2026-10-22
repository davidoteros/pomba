from rest_framework import serializers
from .models import Item, ItemVersion
from .services import ItemService, mime_previsualizable


class ItemSerializer(serializers.ModelSerializer):
    tiene_hijos = serializers.BooleanField(read_only=True)
    file = serializers.FileField(allow_empty_file=True, required=False, allow_null=True)
    # Fuente de verdad para saver si algo se puede previsualizar o no (Queremos evitar inyecciones)
    previsualizable = serializers.SerializerMethodField()

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

    def get_previsualizable(self, obj):
        return obj.tipo == Item.Tipo.ARCHIVO and mime_previsualizable(obj.mime_type) is not None

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
