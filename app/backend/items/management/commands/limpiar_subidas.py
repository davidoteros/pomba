from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from items.services import ItemService


class Command(BaseCommand):
    help = (
        "Borra de Garage los ficheros de subidas abandonadas (pases caducados). "
        "Con --barrer compara además el bucket entero con la BD."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--barrer',
            action='store_true',
            help='Lista los huérfanos del bucket (más de un día sin fila en la BD) y los ficheros rotos.',
        )
        parser.add_argument(
            '--borrar',
            action='store_true',
            help='Con --barrer, borra los huérfanos listados.',
        )

    def handle(self, *args, **opciones):
        if opciones['borrar'] and not opciones['barrer']:
            raise CommandError("--borrar solo vale junto a --barrer.")

        pases, objetos = ItemService.limpiar_subidas_caducadas()
        self.stdout.write(self.style.SUCCESS(
            f"Pases caducados borrados: {pases} ({objetos} keys enviadas a Garage)."
        ))

        if opciones['barrer']:
            self.barrer(opciones['borrar'])

    def barrer(self, borrar):
        huerfanos, rotos = ItemService.revisar_bucket()

        total = sum(o['Size'] for o in huerfanos)
        self.stdout.write(f"Huérfanos en Garage: {len(huerfanos)} ({total} bytes)")
        for o in huerfanos:
            self.stdout.write(f"  {o['Key']}  {o['Size']} B  {timezone.localtime(o['LastModified']):%Y-%m-%d %H:%M}")

        # Solo se listan: arreglar una fila sin fichero lo decide una persona
        self.stdout.write(f"Rotos (en la BD pero no en Garage): {len(rotos)}")
        for key in rotos:
            self.stdout.write(self.style.WARNING(f"  {key}"))

        if borrar and huerfanos:
            ItemService.delete_s3_keys([o['Key'] for o in huerfanos], settings.AWS_STORAGE_BUCKET_NAME)
            self.stdout.write(self.style.SUCCESS(f"Borrados {len(huerfanos)} huérfanos."))
        elif huerfanos:
            self.stdout.write("Nada borrado. Para borrarlos: --barrer --borrar")
