from django.core.management.base import BaseCommand

from items.models import Item
from items.services import ItemService, MIME_CON_MINIATURA, PREVIEW_FALLIDA


class Command(BaseCommand):
    help = "Genera la miniatura de la tabla de las imágenes que aún no la tienen (subidas antes de existir)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--rehacer',
            action='store_true',
            help='Regenera también las que ya tienen miniatura o fallaron.',
        )

    def handle(self, *args, **opciones):
        items = Item.objects.filter(
            tipo=Item.Tipo.ARCHIVO,
            mime_type__in=MIME_CON_MINIATURA,
            eliminado=False,
        )
        if not opciones['rehacer']:
            # Las que fallaron se reintentan solo con --rehacer.
            items = items.filter(miniatura_key='')

        total = items.count()
        self.stdout.write(f"Items a procesar: {total}")

        hechos = 0
        for item in items:
            ItemService.generar_miniatura(item)
            if item.miniatura_key and item.miniatura_key != PREVIEW_FALLIDA:
                hechos += 1
                self.stdout.write(f"  OK  {item.id} {item.nombre} -> {item.miniatura_key}")
            else:
                self.stdout.write(self.style.WARNING(f"  --  {item.id} {item.nombre}: sin miniatura"))

        self.stdout.write(self.style.SUCCESS(f"Generadas {hechos} de {total}."))
