import io
import logging
import os
import uuid
import zipfile

import boto3
import cairosvg
from botocore.client import Config
from botocore.exceptions import ClientError
from elasticsearch import Elasticsearch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Exists, Max, OuterRef
from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError

from .documents import ItemDocument
from .extractors import extraer
from .models import Item, ItemVersion

logger = logging.getLogger(__name__)


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
        Extrae las keys de S3 de los items tipo archivo, incluidos los PNG de previsualización generados por el servidor.
        """
        keys = list(
            items_qs.exclude(file="").exclude(file__isnull=True).values_list("file", flat=True)
        )
        keys += list(
            items_qs.exclude(preview_key="")
            .exclude(preview_key=PREVIEW_FALLIDA)
            .values_list("preview_key", flat=True)
        )
        return keys
    
    @staticmethod
    def delete_s3_keys(keys, bucket_name):
        if not keys:
            return

        s3 = ItemService.get_s3_client()

        for i in range(0, len(keys), 1000):
            batch = keys[i:i + 1000]
            s3.delete_objects(
                Bucket=bucket_name,
                Delete={
                    "Objects": [{"Key": key} for key in batch],
                    "Quiet": True,
                }
            )

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
            raise ValidationError("Archivo requerido")
        
        # Guardo el fichero real en Garage a través de Django
        item.file = fichero

        item.tamano_bytes = fichero.size
        item.mime_type = fichero.content_type

        return ItemService.guardar_item(item)        


    @staticmethod
    def mover_item(item, nueva_carpeta_padre):
        if ItemService.check_cycle(item, nueva_carpeta_padre):
            raise ValidationError("No puedes crear ciclos")

        item.padre = nueva_carpeta_padre

        return ItemService.guardar_item(item)
    
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
        try:
            item.full_clean()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict)
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
    # SECCIÓN 5: Descarga de archivos
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
                "ResponseContentDisposition": f'attachment; filename="{item.nombre}"',
            },
            ExpiresIn=300,
        )

    @staticmethod
    def generar_url_preview(item):
        """Genera una presigned URL para previsualización (image, audio, PDF)."""
        mime = mime_previsualizable(item.mime_type)
        if mime is None:
            raise DRFValidationError({'detail': 'Tipo de archivo no previsualizable.'})

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
            "ResponseContentDisposition": f'inline; filename="{item.nombre}"',
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
    def generar_url_preview_generada(item):
        """
        Presigned URL del PNG que generó el servidor (item.preview_key).
        Siempre image/png: el fichero original nunca se sirve inline.
        """
        if not item.preview_key or item.preview_key == PREVIEW_FALLIDA:
            raise DRFValidationError({'detail': 'Tipo de archivo no previsualizable.'})

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
                "ResponseContentDisposition": f'inline; filename="{item.nombre}.png"',
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
            ExpiresIn=3600,
            HttpMethod='PUT',
        )

    @staticmethod
    def validar_key_subida(usuario, key, subcarpeta=''):
        """
        Comprueba que la key pertenece al usuario, que no está ya registrada y que
        el fichero existe en Garage. Devuelve el tamaño real del objeto.
        """
        prefijo = f"users/{usuario.id}/{subcarpeta}"
        resto = key[len(prefijo):]
        if not key.startswith(prefijo) or not resto or '/' in resto or '..' in key:
            raise DRFValidationError({'key': 'Key no válida.'})

        if Item.objects.filter(file=key).exists() or ItemVersion.objects.filter(file=key).exists():
            raise DRFValidationError({'key': 'Key ya registrada.'})

        try:
            cabecera = ItemService.get_s3_client().head_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key
            )
        except ClientError:
            raise DRFValidationError({'key': 'El archivo no se ha subido.'})

        return cabecera['ContentLength']

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
            logger.warning("No se pudo indexar item %s: %s", item.id, e)

    @staticmethod
    def procesar_item_subido(item):
        """Trabajo posterior a la subida: indexar y vista previa."""
        ItemService.indexar_item(item)
        ItemService.generar_preview_png(item)

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
            logger.warning("No se pudo generar preview de item %s: %s", item.id, e)
            ItemService._marcar_preview_fallida(item)

    @staticmethod
    def _marcar_preview_fallida(item):
        """
        Deja constancia de que la conversión no saldrá, para poder distinguir
        "todavía generándose" de "no la habrá nunca" al previsualizar.
        """
        Item.objects.filter(pk=item.pk).update(preview_key=PREVIEW_FALLIDA)
        item.preview_key = PREVIEW_FALLIDA

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
    # SECCIÓN 6: Control de versiones (solo audio)
    # =========================================================

    @staticmethod
    def listar_versiones(item):
        return item.versiones.all()

    @staticmethod
    def _siguiente_numero_version(item):
        ultimo = item.versiones.aggregate(Max('numero'))['numero__max'] or 0
        return ultimo + 1

    @staticmethod
    def generar_url_presignada_version(item):
        """Genera una presigned PUT URL para subir una nueva versión. El archivo se guarda en la subcarpeta para distinguirlo de la versión activa."""
        ext = os.path.splitext(str(item.file))[1]
        key = f"users/{item.usuario.id}/v/{uuid.uuid4().hex}{ext}"
        url = ItemService.generar_url_presignada_subida(key)
        return url, key

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
            raise DRFValidationError({'detail': 'Tipo de archivo no previsualizable.'})

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
                "ResponseContentDisposition": f'attachment; filename="{nombre_item}"',
            },
            ExpiresIn=300,
        )