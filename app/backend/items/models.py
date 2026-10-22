from django.db import models
from users.models import User
from django.core.exceptions import ValidationError

def upload_item_path(instance, filename):
    return f"users/{instance.usuario.id}/{filename}"

# Create your models here.
class Item(models.Model):

    class Tipo(models.TextChoices):
        ARCHIVO = "archivo", "Archivo"
        CARPETA = "carpeta", "Carpeta"

    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)

    padre = models.ForeignKey(
        "self", 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name="hijos",
    )

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="items")

    # --- STORAGE (SOLO ARCHIVOS) ---
    file = models.FileField(upload_to=upload_item_path, null=True, blank=True)
    tamano_bytes = models.BigIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=100, null=True, blank=True)

    # Key en Garage de un PNG generado por el servidor para previsualizar tipos que no son seguros de servir tal cual (SVG).
    preview_key = models.CharField(max_length=500, blank=True, default='')

    # --- METADATOS ---
    metadatos = models.JSONField(default=dict, blank=True)

    favorito = models.BooleanField(default=False)

    # --- PAPELERA (SOFT DELETE) ---
    eliminado = models.BooleanField(default=False)
    fecha_eliminado = models.DateTimeField(null=True, blank=True)

    # --- Datetime ---
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    def clean(self):
        # Lógica anti-ciclos: no puedes ser padre de ti mismo ni de tus hijos
        if self.padre and self.pk:
            actual = self.padre
            while actual:
                if actual.id == self.pk:
                    raise ValidationError("No puedes crear ciclos en la jerarquía.")
                actual = actual.padre

    # Controlo que al crear una carpeta no se guarden, rutas, ni tamaño de bytes, ni el mime
    def save(self, *args, **kwargs):
        if self.tipo == self.Tipo.CARPETA:
            self.file = None
            self.tamano_bytes = None
            self.mime_type = None
            self.preview_key = ''

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre}"

    class Meta:
        indexes = [
            models.Index(fields=["usuario", "padre", "eliminado"], name="idx_items_navegacion"),
            models.Index(fields=["usuario", "eliminado"], name="idx_items_papelera"),
        ]


class ItemVersion(models.Model):
    """Versión de un archivo de audio. La versión con es_actual=True es la que se reproduce en el explorador."""
    item = models.ForeignKey(Item, related_name='versiones', on_delete=models.CASCADE)
    numero = models.PositiveIntegerField()
    file = models.CharField(max_length=500)
    tamano_bytes = models.BigIntegerField()
    mime_type = models.CharField(max_length=100, blank=True, default='')
    metadatos = models.JSONField(default=dict, blank=True)
    es_actual = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-numero']
        constraints = [
            models.UniqueConstraint(fields=['item', 'numero'], name='unique_item_version'),
        ]
        indexes = [
            models.Index(fields=['item', 'numero'], name='idx_version_item_numero'),
        ]