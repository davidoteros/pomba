import io
import logging
import os
import uuid
import zipfile
from datetime import timedelta

import boto3
import cairosvg
from botocore.client import Config
from botocore.exceptions import ClientError
from elasticsearch import Elasticsearch
from PIL import Image, ImageOps

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Exists, Max, OuterRef, Sum
from django.template.defaultfilters import filesizeformat
from django.utils import timezone
from django.utils.http import content_disposition_header

from .documents import ItemDocument
from .extractors import extraer
from .models import Item, ItemVersion, SubidaPendiente

logger = logging.getLogger(__name__)


# =========================================================
# CUOTA DE ALMACENAMIENTO
# =========================================================
# Las cifras viven en settings porque se configuran por entorno


class CuotaExcedida(Exception):
    """
    El usuario ha superado su cuota de subida.

    Lleva el motivo para que la vista pueda decir si el problema es el fichero
    concreto (demasiado grande) o la cuenta entera (sin espacio libre).
    """

    def __init__(self, mensaje, motivo):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.motivo = motivo  # 'fichero' | 'cuota'


class BorradoGarageFallido(Exception):
    """Garage no pudo borrar alguna key."""


# Tope de elementos por copia: se copia dentro de la misma petición
MAX_ELEMENTOS_COPIA = 1000


# =========================================================
# PREVISUALIZACIÓN
# =========================================================

# Lista blanca de MIME que se pueden servir tal cual (abiertos dentro del navegador).
MIME_PREVISUALIZABLES = frozenset({
    # Imágenes (sin SVG: ya que es texto y admite <script>)
    'image/png', 'image/jpeg', 'image/gif', 'image/webp',
    'image/avif', 'image/bmp', 'image/x-ms-bmp',
    # Audio
    'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav', 'audio/wave',
    'audio/ogg', 'audio/flac', 'audio/x-flac', 'audio/mp4', 'audio/aac',
    'audio/webm', 'audio/opus',
    # Vídeo
    'video/mp4',
    # Documentos
    'application/pdf',
})


MIME_CON_PREVIEW_GENERADA = frozenset({'image/svg+xml'})

LIMITE_SVG_PREVIEW_BYTES = 2 * 1024 * 1024  # 2 MB
ANCHO_PREVIEW_PNG = 1200
PREVIEW_FALLIDA = '/fallida'

# Miniaturas de la tabla: imágenes que Pillow sabe leer (el SVG sale de su PNG generado)
MIME_CON_MINIATURA = frozenset({
    'image/png', 'image/jpeg', 'image/gif', 'image/webp',
    'image/avif', 'image/bmp', 'image/x-ms-bmp', 'image/tiff',
    'image/svg+xml',
})
LADO_MINIATURA = 112  # px: se ve a 28 px y así queda nítida en pantallas Retina
LIMITE_MINIATURA_BYTES = 60 * 1024 * 1024  # 60 MB, como al indexar
LIMITE_MINIATURA_PIXELES = 100_000_000  # 100 Mpx: más que eso no se abre 


def mime_previsualizable(mime_type):
    """
    Normaliza el mime_type (minúsculas y sin parámetros tras ';') y lo devuelve
    solo si está en la lista blanca; si no, devuelve None. Único sitio donde se
    decide qué se puede abrir inline.
    """
    limpio = (mime_type or '').split(';')[0].strip().lower()
    return limpio if limpio in MIME_PREVISUALIZABLES else None


def mime_con_preview_generada(mime_type):
    """True si el tipo se previsualiza mediante un PNG generado por el servidor."""
    return (mime_type or '').split(';')[0].strip().lower() in MIME_CON_PREVIEW_GENERADA


def admite_versiones(item):
    """Si el item tiene control de versiones: encendido en el .env y es un audio."""
    return (
        settings.VERSIONES_AUDIO
        and item.tipo == Item.Tipo.ARCHIVO
        and (item.mime_type or '').startswith('audio/')
    )


def tipo_visor(mime_type):
    """
    Con qué visor debe mostrarlo el frontend: 'imagen', 'audio', 'video', 'pdf' o None.
    """
    limpio = (mime_type or '').split(';')[0].strip().lower()
    if limpio in MIME_CON_PREVIEW_GENERADA:
        return 'imagen'
    if limpio not in MIME_PREVISUALIZABLES:
        return None
    if limpio.startswith('audio/'):
        return 'audio'
    if limpio.startswith('video/'):
        return 'video'
    if limpio == 'application/pdf':
        return 'pdf'
    return 'imagen'


class ItemService:
    # =========================================================
    # SECCIÓN 1: Validaciones y auxiliares
    # =========================================================

    # Validamos que no se den bucles en el arbol (Por ejemplo mover una carpeta dentro de si misma)
    @staticmethod
    def check_cycle(item, nueva_carpeta_padre):
        actual = nueva_carpeta_padre

        while actual:
            if actual.id == item.id:
                return True
            actual = actual.padre

        return False
    
    @staticmethod
    def recolectar_descendientes_id(root_ids, usuario):
        """
        Devuelve todos los ids raíz + descendientes del usuario
        sin hacer N+1.
        """
        all_ids = set(int(i) for i in root_ids)
        frontier = set(all_ids)

        while frontier:
            children = set(
                Item.objects.filter(
                    usuario=usuario,
                    padre_id__in=frontier,
                ).values_list("id", flat=True)
            )
            children -= all_ids
            if not children:
                break

            all_ids |= children
            frontier = children

        return all_ids

    @staticmethod
    def get_s3_client():
        return boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            #Añado esto porque me estaba dando problema para descargar
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )

    @staticmethod
    def get_s3_keys_for_items(items_qs):
        """
        Extrae las keys de S3 de los items tipo archivo, incluidos los PNG de previsualización y las miniaturas que genera el servidor.
        """
        keys = list(
            items_qs.exclude(file="").exclude(file__isnull=True).values_list("file", flat=True)
        )
        keys += list(
            items_qs.exclude(preview_key="")
            .exclude(preview_key=PREVIEW_FALLIDA)
            .values_list("preview_key", flat=True)
        )
        keys += list(
            items_qs.exclude(miniatura_key="")
            .exclude(miniatura_key=PREVIEW_FALLIDA)
            .values_list("miniatura_key", flat=True)
        )
        return keys

    @staticmethod
    def claves_del_usuario(usuario):
        """Todas las keys de Garage de un usuario: items (papelera incluida), previews, versiones y subidas a medias."""
        claves = ItemService.get_s3_keys_for_items(Item.objects.filter(usuario=usuario))
        claves += ItemVersion.objects.filter(item__usuario=usuario).values_list('file', flat=True)
        claves += SubidaPendiente.objects.filter(usuario=usuario).values_list('key', flat=True)
        return sorted(set(claves))

    @staticmethod
    def delete_s3_keys(keys, bucket_name):
        if not keys:
            return

        s3 = ItemService.get_s3_client()

        for i in range(0, len(keys), 1000):
            batch = keys[i:i + 1000]
            respuesta = s3.delete_objects(
                Bucket=bucket_name,
                Delete={
                    "Objects": [{"Key": key} for key in batch],
                    "Quiet": True,
                }
            )
            errores = [e for e in respuesta.get("Errors", []) if e.get("Code") != "NoSuchKey"]
            if errores:
                raise BorradoGarageFallido(f"{len(errores)} keys sin borrar en Garage")

    @staticmethod
    def eliminar_items_fisicos(ids, usuario, bucket_name):
        """
        Borra físicamente items (solo los que están en papelera) y sus descendientes.
        """
        # Filtramos solo items marcados como eliminados para mayor seguridad
        ids_validados = list(
            Item.objects.filter(
                id__in=ids,
                usuario=usuario,
                eliminado=True,
            ).values_list('id', flat=True)
        )

        if not ids_validados:
            return {'deleted_count': 0, 's3_keys_deleted': 0}

        all_ids = ItemService.recolectar_descendientes_id(ids_validados, usuario)
        items_qs = Item.objects.filter(usuario=usuario, id__in=all_ids)
        s3_keys = ItemService.get_s3_keys_for_items(items_qs)

        # También borrar las keys S3 de versiones archivadas antes de que CASCADE las elimine de BD
        version_keys = list(
            ItemVersion.objects.filter(item_id__in=all_ids)
            .exclude(file='').values_list('file', flat=True)
        )
        s3_keys += version_keys
        # Versiones subiéndose: su pase cae en cascada y el fichero quedaría sin rastro
        s3_keys += SubidaPendiente.objects.filter(item_id__in=all_ids).values_list('key', flat=True)

        with transaction.atomic():
            ItemService.delete_s3_keys(s3_keys, bucket_name)
            deleted_count, _ = items_qs.delete()

        return {
            'deleted_count': deleted_count,
            's3_keys_deleted': len(s3_keys),
        }

    
    @staticmethod
    def vaciar_papelera(usuario, bucket_name):
        trash_ids = list(
            Item.objects.filter(usuario=usuario, eliminado=True).values_list("id", flat=True)
        )

        if not trash_ids:
            return {
                "deleted_count": 0,
                "s3_keys_deleted": 0,
            }

        return ItemService.eliminar_items_fisicos(trash_ids, usuario, bucket_name)

    @staticmethod
    def restaurar_items(ids, usuario):
        all_ids = ItemService.recolectar_descendientes_id(ids, usuario)

        return Item.objects.filter(
            usuario=usuario,
            id__in=all_ids
        ).update(
            eliminado=False,
            fecha_eliminado=None
        )

    @staticmethod
    def eliminar_del_indice(item_id):
        """Elimina el documento de Elasticsearch. Si no existe, no hace nada."""
        try:
            ItemDocument.get(id=item_id).delete()
        except Exception as e:
            logger.warning("No se pudo eliminar del índice item %s: %s", item_id, e)

    # =========================================================
    # SECCIÓN 2: Consultas y navegacion
    # =========================================================

    # Prefijos soportados campo:valor
    _PREFIJOS_CAMPO = {
        'artista': ('match', 'meta_artista'),
        'artist':  ('match', 'meta_artista'),
        'album':   ('match', 'meta_album'),
        'titulo':  ('match', 'meta_titulo'),
        'title':   ('match', 'meta_titulo'),
        'genero':  ('match', 'meta_genero'),
        'genre':   ('match', 'meta_genero'),
        'camara':  ('match', 'meta_camara_modelo'),
        'nombre':  ('match', 'nombre'),
        'año':     ('year',  None),
        'year':    ('year',  None),
        'tipo':    ('tipo',  None),
    }

    _TIPOS_MIME = {
        'audio':  'audio/',
        'imagen': 'image/',
        'image':  'image/',
        'video':  'video/',
        'pdf':    'application/pdf',
        'texto':  'text/',
        'text':   'text/',
    }

    @staticmethod
    def _parsear_query(q):
        must_extra = []
        filter_extra = []
        texto_libre = []

        for token in q.split():
            if ':' not in token:
                texto_libre.append(token)
                continue

            prefijo, _, valor = token.partition(':')
            mapping = ItemService._PREFIJOS_CAMPO.get(prefijo.lower())

            if not mapping or not valor:
                texto_libre.append(token)
                continue

            kind, campo = mapping

            if kind == 'match':
                must_extra.append(
                    {'match': {campo: {'query': valor, 'fuzziness': 'AUTO'}}}
                )
            elif kind == 'year':
                try:
                    filter_extra.append({'term': {'meta_anno': int(valor)}})
                except ValueError:
                    texto_libre.append(token)
            elif kind == 'tipo':
                valor_lower = valor.lower()
                if valor_lower == 'carpeta':
                    filter_extra.append({'term': {'tipo': 'carpeta'}})
                else:
                    mime_prefix = ItemService._TIPOS_MIME.get(valor_lower)
                    if mime_prefix:
                        filter_extra.append({'prefix': {'mime_type.keyword': mime_prefix}})
                    else:
                        texto_libre.append(token)

        return must_extra, filter_extra, ' '.join(texto_libre)

    @staticmethod
    def buscar_items(usuario, q):
        es = Elasticsearch(**settings.ELASTICSEARCH_DSL['default'])

        must_extra, filter_extra, texto_libre = ItemService._parsear_query(q)

        must = []
        if texto_libre:
            must.append({
                'multi_match': {
                    'query': texto_libre,
                    'fields': [
                        'nombre^3', 'contenido^0.5', 'meta_titulo^2',
                        'meta_artista', 'meta_album', 'meta_genero',
                        'meta_camara_marca', 'meta_camara_modelo',
                    ],
                    'fuzziness': 'AUTO',
                }
            })
        must.extend(must_extra)

        bool_query = {
            'filter': [
                {'term': {'usuario_id': usuario.id}},
                {'term': {'eliminado': False}},
                *filter_extra,
            ],
        }
        if must:
            bool_query['must'] = must


        kwargs = {'index': 'items', 'size': 50, 'query': {'bool': bool_query}}
        if texto_libre:
            kwargs['min_score'] = 1.0
        respuesta = es.search(**kwargs)
        ids = [int(hit['_id']) for hit in respuesta['hits']['hits']]

        if not ids:
            return []

        hijos = Item.objects.filter(padre=OuterRef('pk'), eliminado=False)
        items_map = {
            item.id: item
            for item in Item.objects.filter(
                id__in=ids, usuario=usuario, eliminado=False
            ).annotate(tiene_hijos=Exists(hijos))
        }
        return [items_map[id_] for id_ in ids if id_ in items_map]

    @staticmethod
    def obtener_breadcrumb(usuario, carpeta_id):
        ruta_base = [{"id": None, "label": "Inicio"}]
        
        # Si no hay ID o es la raíz, devolvemos solo inicio
        if not carpeta_id:
            return ruta_base

        try:
            # Aseguro que id sea un entero para no tener problema
            id_actual = int(carpeta_id)
        except (ValueError, TypeError):
            return ruta_base

        # 1. Traemos TODAS las carpetas (incluidas las eliminadas)
        carpetas = Item.objects.filter(
            usuario=usuario, 
            tipo='carpeta'
        ).values('id', 'nombre', 'padre_id')

        # 2. Mapa en memoria
        mapa_carpetas = {c['id']: c for c in carpetas}

        # 3. Construcción del map
        nodos_padre = []

        while id_actual is not None:
            carpeta = mapa_carpetas.get(id_actual)
            
            if not carpeta:
                # Si no encontramos la carpeta en el mapa puede ser que el ID no exista o no sea del usuario
                break
            
            nodos_padre.append({
                "id": carpeta['id'],
                "label": carpeta['nombre']
            })
            
            # Saltamos al padre
            id_actual = carpeta['padre_id']

        # 4. Invertimos para ir de Raíz -> Hijo
        ruta_base.extend(reversed(nodos_padre))
        return ruta_base

    # =========================================================
    # SECCIÓN 3: Operaciones de escritura (CRUD)
    # =========================================================

    @staticmethod
    def crear_item(usuario, datos, fichero=None): 
        # Creo el item base
        item = Item(usuario=usuario, **datos)

        # Si es Carpeta
        if item.tipo == Item.Tipo.CARPETA:
            return ItemService.guardar_item(item)
        
        # Si es Archivo
        if not fichero:
            raise DjangoValidationError("Archivo requerido")
        
        # Guardo el fichero real en Garage a través de Django
        item.file = fichero

        item.tamano_bytes = fichero.size
        item.mime_type = fichero.content_type

        return ItemService.guardar_item(item)        


    @staticmethod
    def mover_item(item, nueva_carpeta_padre):
        if ItemService.check_cycle(item, nueva_carpeta_padre):
            raise DjangoValidationError("No puedes crear ciclos")

        # Como al subir: si el nombre ya está en el destino, se numera
        if item.padre != nueva_carpeta_padre:
            item.nombre = ItemService._nombre_disponible(item.usuario, item.nombre, nueva_carpeta_padre)
        item.padre = nueva_carpeta_padre

        return ItemService.guardar_item(item)

    @staticmethod
    def _arbol_para_copiar(raices, usuario):
        """Las raíces y lo que cuelga de ellas fuera de la papelera, cada carpeta antes que sus hijos."""
        orden = list(raices)
        vistos = {r.id for r in raices}
        nivel = [r.id for r in raices if r.tipo == Item.Tipo.CARPETA]
        while nivel and len(orden) <= MAX_ELEMENTOS_COPIA:
            hijos = [
                h for h in Item.objects.filter(usuario=usuario, padre_id__in=nivel, eliminado=False).order_by('id')
                if h.id not in vistos
            ]
            orden += hijos
            vistos.update(h.id for h in hijos)
            nivel = [h.id for h in hijos if h.tipo == Item.Tipo.CARPETA]
        return orden

    @staticmethod
    def copiar_items(ids, destino, usuario):
        """
        Copia items (con el contenido de las carpetas) a destino y devuelve las copias.
        Una copia es un fichero nuevo, con su propio objeto en Garage (como Nextcloud, no un alias).
        Todo o nada: si no cabe o Garage falla a mitad, no queda ninguna copia.
        """
        raices = list(Item.objects.filter(id__in=ids, usuario=usuario, eliminado=False).order_by('id'))
        if destino and any(ItemService.check_cycle(r, destino) for r in raices):
            raise DjangoValidationError('Una carpeta no puede ir dentro de sí misma.')
        orden = ItemService._arbol_para_copiar(raices, usuario)
        if len(orden) > MAX_ELEMENTOS_COPIA:
            raise DjangoValidationError(f'No se pueden copiar más de {MAX_ELEMENTOS_COPIA} elementos a la vez.')
        total = sum(i.tamano_bytes or 0 for i in orden if i.tipo == Item.Tipo.ARCHIVO)

        s3 = ItemService.get_s3_client()
        bucket = settings.AWS_STORAGE_BUCKET_NAME
        ids_raiz = {r.id for r in raices}
        copias = {}
        keys_copiadas = []
        try:
            with transaction.atomic():
                # La misma llave que al subir (punto 28): comprobar y ocupar sitio de una vez
                ItemService._bloquear_usuario(usuario)
                ItemService.comprobar_espacio_libre(usuario, total)
                for original in orden:
                    es_raiz = original.id in ids_raiz
                    padre = destino if es_raiz else copias[original.padre_id]
                    copia = Item(
                        usuario=usuario,
                        nombre=ItemService._nombre_disponible(usuario, original.nombre, padre) if es_raiz else original.nombre,
                        tipo=original.tipo,
                        padre=padre,
                        tamano_bytes=original.tamano_bytes,
                        mime_type=original.mime_type,
                        metadatos=dict(original.metadatos or {}),
                    )
                    if original.tipo == Item.Tipo.ARCHIVO and original.file:
                        # Garage copia por dentro, sin bajar ni volver a subir los bytes
                        _, extension = os.path.splitext(str(original.file))
                        key = f"files/{uuid.uuid4().hex}{extension}"
                        s3.copy_object(Bucket=bucket, Key=key, CopySource={'Bucket': bucket, 'Key': str(original.file)})
                        keys_copiadas.append(key)
                        copia.file = key
                    ItemService.guardar_item(copia)
                    # Como al subir: un audio nace con su versión 1 (el mismo objeto, sin bytes extra)
                    if copia.file and (copia.mime_type or '').startswith('audio/'):
                        ItemVersion.objects.create(
                            item=copia, numero=1, file=str(copia.file), tamano_bytes=copia.tamano_bytes or 0,
                            mime_type=copia.mime_type, metadatos={}, es_actual=True,
                        )
                    copias[original.id] = copia
        except Exception:
            try:
                ItemService.delete_s3_keys(keys_copiadas, bucket)
            except Exception:
                logger.exception('No se pudieron borrar de Garage %d copias a medias', len(keys_copiadas))
            raise
        return list(copias.values())

    @staticmethod
    def procesar_copias(copias):
        """Vista previa de los SVG y miniaturas de las copias; el índice de búsqueda ya se actualiza solo al guardar."""
        for copia in copias:
            ItemService.generar_preview_png(copia)
            ItemService.generar_miniatura(copia)
    
    @staticmethod
    def _nombre_disponible(usuario, nombre, padre):
        existe = Item.objects.filter(
            usuario=usuario, padre=padre, nombre=nombre, eliminado=False
        ).exists()
        if not existe:
            return nombre

        base, ext = os.path.splitext(nombre)
        contador = 1
        while True:
            candidato = f"{base} ({contador}){ext}"
            if not Item.objects.filter(
                usuario=usuario, padre=padre, nombre=candidato, eliminado=False
            ).exists():
                return candidato
            contador += 1

    @staticmethod
    def guardar_item(item):
        item.full_clean()
        item.save()
        return item

    # =========================================================
    # SECCIÓN 4: Gestión de estados (Papelera, Favoritos etc.)
    # =========================================================

    # Método Soft Delete - Mandar a la papelera
    @staticmethod
    def mover_a_papelera(ids, usuario):
        all_ids = ItemService.recolectar_descendientes_id(ids, usuario)

        return Item.objects.filter(
            usuario=usuario,
            id__in=all_ids
        ).update(
            eliminado=True,
            fecha_eliminado=timezone.now()
        )
    
    @staticmethod
    def marcar_favorito(item_id, usuario):
        item = Item.objects.get(id=item_id, usuario=usuario)
        item.favorito = not item.favorito
        item.save(update_fields=['favorito'])
        return item.favorito

    # =========================================================
    # SECCIÓN 5: Cuota de almacenamiento
    # =========================================================

    @staticmethod
    def espacio_usado(usuario):
        """
        Bytes que el usuario ocupa de verdad en Garage.

        Cuenta la papelera, porque un item eliminado sigue ocupando disco hasta que se vacía, y suma las versiones archivadas.
        """
        items = Item.objects.filter(
            usuario=usuario, tipo=Item.Tipo.ARCHIVO,
        ).aggregate(total=Sum('tamano_bytes'))['total'] or 0

        versiones = ItemVersion.objects.filter(
            item__usuario=usuario, es_actual=False,
        ).aggregate(total=Sum('tamano_bytes'))['total'] or 0

        return items + versiones

    @staticmethod
    def espacio_pendiente(usuario):
        """
        Bytes ya prometidos en pases de subida que aún no se han confirmado.

        Hay que contarlos: el PUT presignado no pasa por Django, así que sin esto
        se podrían pedir cientos de pases y llenar el disco sin confirmar ninguno,
        con la base de datos creyendo que el usuario ocupa cero.
        """
        limite = timezone.now() - timedelta(minutes=settings.SUBIDA_PENDIENTE_MINUTOS)
        return SubidaPendiente.objects.filter(
            usuario=usuario, fecha_creacion__gte=limite,
        ).aggregate(total=Sum('tamano_declarado'))['total'] or 0

    @staticmethod
    def espacio_ocupado(usuario):
        return ItemService.espacio_usado(usuario) + ItemService.espacio_pendiente(usuario)

    @staticmethod
    def resumen_espacio(usuario):
        """Lo que enseña la barra de espacio, calculado aquí para que Vue no repita la cuenta."""
        ocupado = ItemService.espacio_ocupado(usuario)
        return {
            'ocupado': ocupado,
            'libre': max(settings.CUOTA_USUARIO_BYTES - ocupado, 0),
            'cuota': settings.CUOTA_USUARIO_BYTES,
            'limite_fichero': settings.LIMITE_FICHERO_BYTES,
        }

    @staticmethod
    def _bloquear_usuario(usuario):
        """Bloquea la fila del usuario hasta el final de la transacción: sus cuentas de cuota van de una en una."""
        get_user_model().objects.select_for_update().get(pk=usuario.pk)

    @staticmethod
    def comprobar_cuota(usuario, tamano_bytes):
        """
        Lanza CuotaExcedida si el fichero pasa del límite por fichero o si no cabe
        en lo que le queda libre al usuario. Único sitio donde se decide esto.
        """
        if tamano_bytes > settings.LIMITE_FICHERO_BYTES:
            raise CuotaExcedida(
                f'El archivo supera el máximo de {filesizeformat(settings.LIMITE_FICHERO_BYTES)} por fichero.',
                motivo='fichero',
            )
        ItemService.comprobar_espacio_libre(usuario, tamano_bytes)

    @staticmethod
    def comprobar_espacio_libre(usuario, tamano_bytes):
        """Lanza CuotaExcedida si tamano_bytes no cabe en lo libre. Copiar usa solo esto: sus ficheros ya pasaron el límite."""
        ocupado = ItemService.espacio_ocupado(usuario)
        if ocupado + tamano_bytes > settings.CUOTA_USUARIO_BYTES:
            libre = max(settings.CUOTA_USUARIO_BYTES - ocupado, 0)
            raise CuotaExcedida(
                f'Sin espacio: quedan {filesizeformat(libre)} libres de {filesizeformat(settings.CUOTA_USUARIO_BYTES)}.',
                motivo='cuota',
            )

    # =========================================================
    # SECCIÓN 6: Subida de archivos
    # =========================================================

    @staticmethod
    def generar_url_presignada_subida(key):
        """
        Genera una presigned URL para que el navegador haga PUT directamente a Garage.
        Usa el endpoint PÚBLICO para que la firma SigV4 coincida con el host
        que verá el navegador.
        """
        public_endpoint = getattr(settings, 'GARAGE_PUBLIC_URL', settings.AWS_S3_ENDPOINT_URL)

        client = boto3.client(
            's3',
            endpoint_url=public_endpoint,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'},
            ),
        )

        return client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': key,
            },
            # Corto a propósito: el pase sirve para una subida que empieza ya, no para
            # guardarlo y usarlo una hora después.
            ExpiresIn=900,
            HttpMethod='PUT',
        )

    @staticmethod
    def entregar_pase_subida(usuario, nombre, tamano_bytes, item=None):
        """
        Comprueba la cuota, apunta la subida pendiente y devuelve (url, key).
        """
        tamano_bytes = int(tamano_bytes)

        _, extension = os.path.splitext(nombre)
        subcarpeta = 'v/' if item is not None else ''
        key = f"files/{subcarpeta}{uuid.uuid4().hex}{extension}"

        # Comprobar y apuntar bajo la misma llave: sin ella, pases simultáneos ven el mismo hueco
        with transaction.atomic():
            ItemService._bloquear_usuario(usuario)
            ItemService.comprobar_cuota(usuario, tamano_bytes)
            SubidaPendiente.objects.create(
                key=key,
                usuario=usuario,
                item=item,
                tamano_declarado=tamano_bytes,
            )
        return ItemService.generar_url_presignada_subida(key), key

    @staticmethod
    def validar_key_subida(usuario, key, item=None):
        """
        Comprueba que esta key es un pase que el servidor entregó a este usuario
        (y a este item, si es una versión), que no ha caducado y que el fichero
        está en Garage. Devuelve el tamaño real y consume el pase.

        El tamaño real manda sobre el declarado: el PUT no pasa por Django, así que
        se puede declarar 1 byte y subir 2 GB. Si pasa eso, se borra el objeto.

        Llamarla en un transaction.atomic() junto al registro, para que la llave dure hasta que exista el Item.
        """
        limite = timezone.now() - timedelta(minutes=settings.SUBIDA_PENDIENTE_MINUTOS)
        pendiente = SubidaPendiente.objects.filter(
            key=key, usuario=usuario, item=item, fecha_creacion__gte=limite,
        ).first()
        if pendiente is None:
            raise DjangoValidationError({'key': 'Key no válida.'})

        # El pase se borra al confirmar, así que una key ya
        # registrada no debería llegar hasta aquí nunca.
        if Item.objects.filter(file=key).exists() or ItemVersion.objects.filter(file=key).exists():
            raise DjangoValidationError({'key': 'Key ya registrada.'})

        try:
            cabecera = ItemService.get_s3_client().head_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key
            )
        except ClientError:
            raise DjangoValidationError({'key': 'El archivo no se ha subido.'})

        tamano_real = cabecera['ContentLength']

        if tamano_real > pendiente.tamano_declarado:
            ItemService._borrar_objeto(key)
            pendiente.delete()
            raise DjangoValidationError(
                {'key': 'El archivo subido es mayor que el tamaño declarado.'}
            )

        # La llave se toma después del head_object, para no tenerla puesta mientras se espera a Garage
        with transaction.atomic():
            ItemService._bloquear_usuario(usuario)
            # Si otra petición ya consumió este pase, esta no puede registrar la key otra vez
            borrados, _ = SubidaPendiente.objects.filter(pk=pendiente.pk).delete()
            if not borrados:
                raise DjangoValidationError({'key': 'Key no válida.'})
            try:
                ItemService.comprobar_cuota(usuario, tamano_real)
            except CuotaExcedida:
                ItemService._borrar_objeto(key)
                raise

        return tamano_real

    @staticmethod
    def _borrar_objeto(key):
        """Borra un objeto de Garage sin romper si ya no está."""
        try:
            ItemService.get_s3_client().delete_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key
            )
        except ClientError:
            logger.warning("No se pudo borrar el objeto huérfano %r", key)

    # Margen tras caducar el pase, para no pisar una confirmación que esté en marcha.
    _MARGEN_LIMPIEZA = timedelta(minutes=10)

    @staticmethod
    def limpiar_subidas_caducadas():
        """
        Borra de Garage y de la BD los pases caducados. Devuelve (pases, objetos) borrados.

        Garage primero: si falla, los pases se quedan y la próxima ejecución lo reintenta.
        """
        limite = (timezone.now() - timedelta(minutes=settings.SUBIDA_PENDIENTE_MINUTOS)
                  - ItemService._MARGEN_LIMPIEZA)
        caducadas = dict(
            SubidaPendiente.objects.filter(fecha_creacion__lt=limite).values_list('pk', 'key')
        )
        claves = set(caducadas.values())
        # Nunca se borra un fichero que ya pertenezca a un item o a una versión
        claves -= set(Item.objects.filter(file__in=claves).values_list('file', flat=True))
        claves -= set(ItemVersion.objects.filter(file__in=claves).values_list('file', flat=True))

        ItemService.delete_s3_keys(sorted(claves), settings.AWS_STORAGE_BUCKET_NAME)
        SubidaPendiente.objects.filter(pk__in=caducadas).delete()
        return len(caducadas), len(claves)

    @staticmethod
    def claves_registradas():
        """Keys de Garage que la BD dice que existen: items, previews, miniaturas, versiones y fotos de perfil."""
        claves = set(Item.objects.exclude(file='').exclude(file__isnull=True).values_list('file', flat=True))
        claves |= set(
            Item.objects.exclude(preview_key='').exclude(preview_key=PREVIEW_FALLIDA)
            .values_list('preview_key', flat=True)
        )
        claves |= set(
            Item.objects.exclude(miniatura_key='').exclude(miniatura_key=PREVIEW_FALLIDA)
            .values_list('miniatura_key', flat=True)
        )
        claves |= set(ItemVersion.objects.values_list('file', flat=True))
        claves |= set(
            get_user_model().objects.exclude(foto_perfil='').exclude(foto_perfil__isnull=True)
            .values_list('foto_perfil', flat=True)
        )
        return claves

    @staticmethod
    def revisar_bucket(antiguedad=timedelta(days=1)):
        """
        Compara el bucket entero con la BD. Devuelve (huérfanos, rotos):
        huérfanos son objetos sin fila que llevan más de `antiguedad` en Garage;
        rotos son keys registradas cuyo objeto no está en Garage.
        """
        # Primero el bucket y luego la BD: lo que se confirme entre medias sale como registrado
        paginas = ItemService.get_s3_client().get_paginator('list_objects_v2').paginate(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        )
        objetos = {o['Key']: o for pagina in paginas for o in pagina.get('Contents', [])}
        registradas = ItemService.claves_registradas()
        pendientes = set(SubidaPendiente.objects.values_list('key', flat=True))

        # El margen cubre las subidas en curso: el objeto llega antes que su Item
        limite = timezone.now() - antiguedad
        huerfanos = [
            o for k, o in sorted(objetos.items())
            if k not in registradas and k not in pendientes and o['LastModified'] < limite
        ]
        rotos = sorted(registradas - objetos.keys())
        return huerfanos, rotos

    @staticmethod
    def registrar_item_subido(usuario, nombre, padre, key, tamano_bytes, mime_type):
        nombre = ItemService._nombre_disponible(usuario, nombre, padre)
        mime_type = mime_type or 'application/octet-stream'
        item = Item(
            usuario=usuario,
            nombre=nombre,
            tipo=Item.Tipo.ARCHIVO,
            padre=padre,
            tamano_bytes=tamano_bytes or 0,
            mime_type=mime_type,
        )
        item.file = key
        with transaction.atomic():
            ItemService.guardar_item(item)
            if mime_type.startswith('audio/'):
                ItemVersion.objects.create(
                    item=item,
                    numero=1,
                    file=key,
                    tamano_bytes=int(tamano_bytes or 0),
                    mime_type=mime_type,
                    metadatos={},
                    es_actual=True,
                )
        return item

    # =========================================================
    # SECCIÓN 7: Procesado posterior a la subida (índice y vista previa)
    # =========================================================

    # Si el archivo es pequeño, lo descarga de S3 para extraer metadatos; si es demasiado grande lo ignora.
    _LIMITE_DESCARGA_BYTES = {
        'audio': 100 * 1024 * 1024,  # 100 MB
        'image':  60 * 1024 * 1024,  # 60 MB
        'text':    10 * 1024 * 1024,  # 10 MB
    }

    @staticmethod
    def indexar_item(item):
        """
        Extrae metadatos del archivo y actualiza el índice de Elasticsearch.
        Si el archivo supera el límite para su tipo, se indexa solo con los
        metadatos básicos (nombre, tamaño…) sin descargar el contenido.
        """
        if item.tipo != Item.Tipo.ARCHIVO or not item.file:
            return
        try:
            mime_prefix = (item.mime_type or '').split('/')[0].lower()
            limite = ItemService._LIMITE_DESCARGA_BYTES.get(mime_prefix)
            tamano = item.tamano_bytes or 0

            if limite is not None and tamano <= limite:
                s3 = ItemService.get_s3_client()
                obj = s3.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=str(item.file))
                datos = obj['Body'].read()

                resultado = extraer(datos, item.mime_type or '', tamano)
                metadatos = resultado['metadatos']
                if resultado['contenido']:
                    metadatos['contenido'] = resultado['contenido']

                item.metadatos = metadatos
                Item.objects.filter(pk=item.pk).update(metadatos=metadatos)

            ItemDocument().update(item)
        except Exception as e:
            logger.warning("No se pudo indexar item %s: %r", item.id, e)

    @staticmethod
    def procesar_item_subido(item):
        """Trabajo posterior a la subida: indexar, vista previa y miniatura."""
        ItemService.indexar_item(item)
        ItemService.generar_preview_png(item)
        ItemService.generar_miniatura(item)

    @staticmethod
    def generar_preview_png(item):
        """
        Genera un PNG a partir de un item cuyo tipo no es seguro servir tal cual (SVG) y guarda su key en item.preview_key.
        """
        if item.tipo != Item.Tipo.ARCHIVO or not item.file:
            return
        if mime_previsualizable(item.mime_type) is not None:
            return  # ya se puede servir tal cual, no hace falta convertirlo
        if (item.mime_type or '').split(';')[0].strip().lower() not in MIME_CON_PREVIEW_GENERADA:
            return

        # limitamos el tamaño del SVG  para no bloquear la CPU del servidor.
        if (item.tamano_bytes or 0) > LIMITE_SVG_PREVIEW_BYTES:
            logger.info("SVG demasiado grande para previsualizar: item %s", item.id)
            ItemService._marcar_preview_fallida(item)
            return

        try:
            s3 = ItemService.get_s3_client()
            obj = s3.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=str(item.file))
            datos = obj['Body'].read()

            png = cairosvg.svg2png(bytestring=datos, output_width=ANCHO_PREVIEW_PNG)

            key = f"users/{item.usuario_id}/p/{uuid.uuid4().hex}.png"
            s3.put_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=key,
                Body=png,
                ContentType='image/png',
            )
            Item.objects.filter(pk=item.pk).update(preview_key=key)
            item.preview_key = key
        except Exception as e:
            logger.warning("No se pudo generar preview de item %s: %r", item.id, e)
            ItemService._marcar_preview_fallida(item)

    @staticmethod
    def generar_miniatura(item):
        """
        Crea la miniatura cuadrada WebP que enseña la tabla y guarda su key en item.miniatura_key.
        El SVG se hace desde su PNG generado: nunca se abre el SVG con Pillow.
        """
        if item.tipo != Item.Tipo.ARCHIVO or not item.file:
            return
        mime = (item.mime_type or '').split(';')[0].strip().lower()
        if mime not in MIME_CON_MINIATURA:
            return
        if mime_con_preview_generada(mime):
            if not item.preview_key or item.preview_key == PREVIEW_FALLIDA:
                ItemService._marcar_miniatura_fallida(item)
                return
            origen = item.preview_key
        elif (item.tamano_bytes or 0) > LIMITE_MINIATURA_BYTES:
            logger.info("Imagen demasiado grande para la miniatura: item %s", item.id)
            ItemService._marcar_miniatura_fallida(item)
            return
        else:
            origen = str(item.file)

        try:
            s3 = ItemService.get_s3_client()
            datos = s3.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=origen)['Body'].read()

            with Image.open(io.BytesIO(datos)) as imagen:
                if imagen.width * imagen.height > LIMITE_MINIATURA_PIXELES:
                    raise ValueError(f"{imagen.width}x{imagen.height} px")
                # En JPEG decodifica ya reducida: mucho más rápido con fotos grandes
                imagen.draft('RGB', (LADO_MINIATURA * 2, LADO_MINIATURA * 2))
                imagen = ImageOps.exif_transpose(imagen)
                con_alfa = imagen.mode in ('RGBA', 'LA', 'PA') or 'transparency' in imagen.info
                imagen = imagen.convert('RGBA' if con_alfa else 'RGB')
                miniatura = ImageOps.fit(imagen, (LADO_MINIATURA, LADO_MINIATURA), Image.Resampling.LANCZOS)

            salida = io.BytesIO()
            miniatura.save(salida, 'WEBP', quality=80, method=6)

            key = f"users/{item.usuario_id}/m/{uuid.uuid4().hex}.webp"
            s3.put_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=key,
                Body=salida.getvalue(),
                ContentType='image/webp',
            )
            anterior = item.miniatura_key
            Item.objects.filter(pk=item.pk).update(miniatura_key=key)
            item.miniatura_key = key
            if anterior and anterior != PREVIEW_FALLIDA:
                ItemService._borrar_objeto(anterior)
        except Exception as e:
            logger.warning("No se pudo generar la miniatura de item %s: %r", item.id, e)
            ItemService._marcar_miniatura_fallida(item)

    @staticmethod
    def _marcar_miniatura_fallida(item):
        """Sin miniatura para siempre: la tabla deja el icono y no la vuelve a pedir."""
        Item.objects.filter(pk=item.pk).update(miniatura_key=PREVIEW_FALLIDA)
        item.miniatura_key = PREVIEW_FALLIDA

    @staticmethod
    def _marcar_preview_fallida(item):
        """
        Deja constancia de que la conversión no saldrá, para poder distinguir
        "todavía generándose" de "no la habrá nunca" al previsualizar.
        """
        Item.objects.filter(pk=item.pk).update(preview_key=PREVIEW_FALLIDA)
        item.preview_key = PREVIEW_FALLIDA

    # =========================================================
    # SECCIÓN 8: Descarga de archivos
    # =========================================================

    @staticmethod
    def generar_url_descarga(item):
        """
        Genera una presigned URL para descarga directa de un único archivo.
        """
        public_endpoint = getattr(settings, "GARAGE_PUBLIC_URL", settings.AWS_S3_ENDPOINT_URL)

        client = boto3.client(
            "s3",
            endpoint_url=public_endpoint,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )

        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": str(item.file),
                "ResponseContentDisposition": content_disposition_header(True, item.nombre),
            },
            ExpiresIn=300,
        )

    @staticmethod
    def generar_url_preview(item):
        """Genera una presigned URL para previsualización (image, audio, PDF)."""
        mime = mime_previsualizable(item.mime_type)
        if mime is None:
            raise DjangoValidationError({'detail': 'Tipo de archivo no previsualizable.'})

        public_endpoint = getattr(settings, "GARAGE_PUBLIC_URL", settings.AWS_S3_ENDPOINT_URL)

        client = boto3.client(
            "s3",
            endpoint_url=public_endpoint,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )

        params = {
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key": str(item.file),
            "ResponseContentDisposition": content_disposition_header(False, item.nombre),
            # Forzamos el tipo validado; nunca dejamos que Garage use la etiqueta
            # que puso el cliente al subir.
            "ResponseContentType": mime,
        }

        return client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=300,
        )

    @staticmethod
    def generar_url_miniatura(item):
        """Presigned URL de la miniatura WebP; siempre image/webp e inline."""
        if not item.miniatura_key or item.miniatura_key == PREVIEW_FALLIDA:
            raise DjangoValidationError({'detail': 'Este archivo no tiene miniatura.'})

        public_endpoint = getattr(settings, "GARAGE_PUBLIC_URL", settings.AWS_S3_ENDPOINT_URL)

        client = boto3.client(
            "s3",
            endpoint_url=public_endpoint,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": item.miniatura_key,
                "ResponseContentDisposition": content_disposition_header(False, f"{item.nombre}.webp"),
                "ResponseContentType": "image/webp",
            },
            ExpiresIn=300,
        )

    @staticmethod
    def generar_url_preview_generada(item):
        """
        Presigned URL del PNG que generó el servidor (item.preview_key).
        Siempre image/png: el fichero original nunca se sirve inline.
        """
        if not item.preview_key or item.preview_key == PREVIEW_FALLIDA:
            raise DjangoValidationError({'detail': 'Tipo de archivo no previsualizable.'})

        public_endpoint = getattr(settings, "GARAGE_PUBLIC_URL", settings.AWS_S3_ENDPOINT_URL)

        client = boto3.client(
            "s3",
            endpoint_url=public_endpoint,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": item.preview_key,
                "ResponseContentDisposition": content_disposition_header(False, f"{item.nombre}.png"),
                "ResponseContentType": "image/png",
            },
            ExpiresIn=300,
        )

    @staticmethod
    def recolectar_archivos_para_zip(root_ids, usuario):
        """
        Recorre el árbol de items y devuelve una lista de manteniendo la estructura de carpetas.
        """
        resultado = []
        pendientes = {int(i): "" for i in root_ids}

        while pendientes:
            items = Item.objects.filter(
                id__in=list(pendientes.keys()),
                usuario=usuario,
                eliminado=False,
            )
            carpetas_con_prefijo = {}

            for item in items:
                prefijo = pendientes[item.id]
                if item.tipo == Item.Tipo.ARCHIVO:
                    resultado.append((item, prefijo + item.nombre))
                elif item.tipo == Item.Tipo.CARPETA:
                    carpetas_con_prefijo[item.id] = prefijo + item.nombre + "/"

            if not carpetas_con_prefijo:
                break

            hijos = Item.objects.filter(
                padre_id__in=carpetas_con_prefijo.keys(),
                usuario=usuario,
                eliminado=False,
            ).values("id", "padre_id")

            pendientes = {
                hijo["id"]: carpetas_con_prefijo[hijo["padre_id"]]
                for hijo in hijos
            }

        return resultado

    @staticmethod
    def stream_zip(archivos_con_ruta, bucket_name):
        """
        Generador que emite el ZIP en chunks descargando un archivo de S3
        cada vez, sin cargar todos en RAM simultáneamente.
        """
        s3 = ItemService.get_s3_client()

        class _Buf(io.RawIOBase):
            def __init__(self):
                self._chunks = []
                self._pos = 0

            def write(self, b):
                data = bytes(b)
                self._chunks.append(data)
                self._pos += len(data)
                return len(data)

            def tell(self):
                return self._pos

            def seek(self, offset, whence=io.SEEK_SET):
                # ZipFile.__init__ llama seek(0, SEEK_END) en modo escritura;
                # lo permitimos como no-op porque ya estamos al final.
                if whence == io.SEEK_END and offset == 0:
                    return self._pos
                raise io.UnsupportedOperation('seek')

            def seekable(self):
                return False

            def readable(self):
                return False

            def writable(self):
                return True

            def pop(self):
                chunks, self._chunks = self._chunks, []
                return chunks

        buf = _Buf()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
            yield from buf.pop()

            for item, zip_path in archivos_con_ruta:
                obj = s3.get_object(Bucket=bucket_name, Key=str(item.file))
                with zf.open(zipfile.ZipInfo(zip_path), 'w', force_zip64=True) as entry:
                    for chunk in obj['Body'].iter_chunks(chunk_size=4 * 1024 * 1024):
                        entry.write(chunk)
                        yield from buf.pop()
                yield from buf.pop()

        yield from buf.pop()

    # =========================================================
    # SECCIÓN 9: Control de versiones (solo audio)
    # =========================================================

    @staticmethod
    def listar_versiones(item):
        return item.versiones.all()

    @staticmethod
    def _siguiente_numero_version(item):
        ultimo = item.versiones.aggregate(Max('numero'))['numero__max'] or 0
        return ultimo + 1

    @staticmethod
    def generar_url_presignada_version(item, tamano_bytes):
        """
        Genera una presigned PUT URL para subir una nueva versión de un item.

        La key va en la subcarpeta `v/` para distinguirla de la versión activa, y el
        pase queda atado al item: así una pendiente de otro item no sirve aquí.
        """
        return ItemService.entregar_pase_subida(
            usuario=item.usuario,
            nombre=str(item.file),
            tamano_bytes=tamano_bytes,
            item=item,
        )

    @staticmethod
    def registrar_version(item, key, tamano_bytes, mime_type):
        """Desactiva la versión activa, crea una nueva ItemVersion marcada como actual y actualiza Item."""
        with transaction.atomic():
            item.versiones.filter(es_actual=True).update(es_actual=False)
            ItemVersion.objects.create(
                item=item,
                numero=ItemService._siguiente_numero_version(item),
                file=key,
                tamano_bytes=int(tamano_bytes or 0),
                mime_type=mime_type or item.mime_type or '',
                metadatos={},
                es_actual=True,
            )
            item.file         = key
            item.tamano_bytes = int(tamano_bytes or 0)
            item.mime_type    = mime_type or item.mime_type
            item.save()
        return item

    @staticmethod
    def activar_version(item, version):
        """Marca la versión seleccionada como activa y actualiza Item sin copiar archivos en S3."""
        with transaction.atomic():
            item.versiones.filter(es_actual=True).update(es_actual=False)
            version.es_actual = True
            version.save(update_fields=['es_actual'])
            item.file         = version.file
            item.tamano_bytes = version.tamano_bytes
            item.mime_type    = version.mime_type
            item.metadatos    = version.metadatos
            item.save()
        return item

    @staticmethod
    def generar_url_preview_version(version):
        """Presigned GET URL (inline) para reproducir una versión archivada directamente en el navegador."""
        mime = mime_previsualizable(version.mime_type)
        if mime is None:
            raise DjangoValidationError({'detail': 'Tipo de archivo no previsualizable.'})

        public_endpoint = getattr(settings, "GARAGE_PUBLIC_URL", settings.AWS_S3_ENDPOINT_URL)
        client = boto3.client(
            "s3",
            endpoint_url=public_endpoint,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        params = {
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key": version.file,
            "ResponseContentDisposition": "inline",
            # Tipo validado; no nos fiamos de la etiqueta del cliente.
            "ResponseContentType": mime,
        }
        return client.generate_presigned_url("get_object", Params=params, ExpiresIn=300)

    @staticmethod
    def eliminar_version(version, bucket_name):
        """Borra la key S3 de una versión archivada y el registro de BD."""
        s3 = ItemService.get_s3_client()
        try:
            s3.delete_object(Bucket=bucket_name, Key=version.file)
        except Exception as e:
            logger.warning("No se pudo borrar versión de S3 %s: %s", version.file, e)
        version.delete()

    @staticmethod
    def generar_url_descarga_version(version, nombre_item):
        """Presigned GET URL (attachment) para descargar una versión archivada."""
        public_endpoint = getattr(settings, "GARAGE_PUBLIC_URL", settings.AWS_S3_ENDPOINT_URL)
        client = boto3.client(
            "s3",
            endpoint_url=public_endpoint,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": version.file,
                "ResponseContentDisposition": content_disposition_header(True, nombre_item),
            },
            ExpiresIn=300,
        )