from django.core.management.base import BaseCommand

from items.models import Item
from items.services import ItemService, MIME_CON_PREVIEW_GENERADA, PREVIEW_FALLIDA


class Command(BaseCommand):
    help = "Genera el PNG de previsualización de los items que aún no lo tienen (SVG subidos antes)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--rehacer',
            action='store_true',
            help='Regenera también los que ya tienen preview.',
        )

    def handle(self, *args, **opciones):
        items = Item.objects.filter(
            tipo=Item.Tipo.ARCHIVO,
            mime_type__in=MIME_CON_PREVIEW_GENERADA,
            eliminado=False,
        )
        if not opciones['rehacer']:
            # Los que fallaron se reintentan solo con --rehacer.
            items = items.filter(preview_key='')

        total = items.count()
        self.stdout.write(f"Items a procesar: {total}")

        hechos = 0
        for item in items:
            # Para que --rehacer vuelva a intentar los marcados como fallidos.
            item.preview_key = ''
            ItemService.generar_preview_png(item)
            item.refresh_from_db(fields=['preview_key'])
            if item.preview_key and item.preview_key != PREVIEW_FALLIDA:
                hechos += 1
                self.stdout.write(f"  OK  {item.id} {item.nombre} -> {item.preview_key}")
            else:
                self.stdout.write(self.style.WARNING(f"  --  {item.id} {item.nombre}: sin preview"))

        self.stdout.write(self.style.SUCCESS(f"Generados {hechos} de {total}."))
