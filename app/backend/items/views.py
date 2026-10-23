import os
import threading
import uuid

from rest_framework import status
from rest_framework.mixins import ListModelMixin, CreateModelMixin
from rest_framework.viewsets import GenericViewSet
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from django.db.models import Exists, OuterRef
from django.http import StreamingHttpResponse
from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers as drf_serializers
from django.conf import settings

from .models import Item, ItemVersion
from .serializers import ItemSerializer, ItemVersionSerializer
from .services import ItemService, mime_previsualizable, mime_con_preview_generada, PREVIEW_FALLIDA


@extend_schema_view(
    retrieve=extend_schema(parameters=[OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.PATH)]),
    update=extend_schema(parameters=[OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.PATH)]),
    partial_update=extend_schema(parameters=[OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.PATH)]),
    destroy=extend_schema(parameters=[OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.PATH)]),
)
class ItemViewSet(ListModelMixin, CreateModelMixin, GenericViewSet):
    serializer_class = ItemSerializer
    parser_classes = (JSONParser,)

    # FILTRADO BASE
    def get_queryset(self):
        user = self.request.user
        qs = Item.objects.filter(usuario=user)

        # Las acciones sobre items (renombrar, descargar_archivo...) solo necesitan filtrar por usuario y que no estén eliminados, sin la lógica de navegación
        if self.action != 'list':
            hijos_activos = Item.objects.filter(padre=OuterRef("pk"), eliminado=False)
            return qs.filter(eliminado=False).annotate(tiene_hijos=Exists(hijos_activos))

        # 1. Parámetros de listado
        carpeta_id = self.request.query_params.get("carpeta")
        es_papelera = self.request.query_params.get("papelera") == "true"
        es_favorito = self.request.query_params.get("favorito") == "true"
        es_reciente = self.request.query_params.get("recientes") == "true"

        # 2. Estado de eliminación (Papelera vs Normal)
        if es_papelera:
            qs = qs.filter(eliminado=True)
        else:
            qs = qs.filter(eliminado=False)

        # 3. Recientes — Los 30 ultimos archivos por fecha de modificacion mas reciente
        if es_reciente:
            hijos = Item.objects.filter(padre=OuterRef("pk"), eliminado=False)
            return qs.filter(tipo=Item.Tipo.ARCHIVO).annotate(tiene_hijos=Exists(hijos)).order_by("-fecha_modificacion")[:30]

        # 4. Lógica de Navegación vs Filtrado
        if carpeta_id:
            qs = qs.filter(padre_id=carpeta_id)
        else:
            if es_favorito:
                qs = qs.filter(favorito=True)
            elif es_papelera:
                # En la raíz de la papelera solo mostramos el nivel superior de cada árbol eliminado
                qs = qs.exclude(padre__eliminado=True)
            else:
                qs = qs.filter(padre__isnull=True)

        # 4. Optimización y orden
        hijos = Item.objects.filter(padre=OuterRef("pk"), eliminado=es_papelera)
        return qs.annotate(tiene_hijos=Exists(hijos)).order_by("-tipo", "nombre")
    
    # MÉTODOS ESTÁNDAR
    @extend_schema(
        parameters=[
            OpenApiParameter('carpeta', OpenApiTypes.INT, description='ID de carpeta a listar'),
            OpenApiParameter('papelera', OpenApiTypes.STR, description='"true" para listar la papelera'),
            OpenApiParameter('favorito', OpenApiTypes.STR, description='"true" para listar favoritos'),
            OpenApiParameter('recientes', OpenApiTypes.STR, description='"true" para listar recientes'),
        ],
        responses=inline_serializer('ItemListResponse', fields={
            'items': ItemSerializer(many=True),
            'breadcrumb': drf_serializers.ListField(child=drf_serializers.DictField()),
        }),
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        carpeta_id = request.query_params.get('carpeta')
        breadcrumb = ItemService.obtener_breadcrumb(request.user, carpeta_id)
        return Response({'items': serializer.data, 'breadcrumb': breadcrumb})


    def perform_create(self, serializer):
        blob = self.request.FILES.get('file')
        item = ItemService.crear_item(
            usuario=self.request.user,
            datos=serializer.validated_data,
            fichero=blob,
        )
        serializer.instance = item

    # =========================================================
    # ACCIONES SOBRE ITEMS
    # =========================================================

    @extend_schema(
        request=inline_serializer('RenombrarRequest', fields={'nombre': drf_serializers.CharField()}),
        responses=inline_serializer('RenombrarResponse', fields={
            'mensaje': drf_serializers.CharField(),
            'nombre': drf_serializers.CharField(),
        }),
    )
    @action(detail=True, methods=['post'])
    def renombrar(self, request, pk=None):
        item = self.get_object()
        nuevo_nombre = request.data.get('nombre', '').strip()
        if not nuevo_nombre:
            return Response(
                {'detail': 'El nombre es obligatorio.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        item.nombre = nuevo_nombre
        try:
            ItemService.guardar_item(item)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        ItemService.indexar_item(item)

        return Response({'mensaje': 'Renombrado correctamente', 'nombre': item.nombre})

    @extend_schema(
        request=inline_serializer('FavoritoRequest', fields={'id': drf_serializers.IntegerField()}),
        responses=inline_serializer('FavoritoResponse', fields={
            'detail': drf_serializers.CharField(),
            'favorito': drf_serializers.BooleanField(),
        }),
    )
    @action(detail=False, methods=['post'])
    def favorito(self, request):
        item_id = request.data.get('id')
        if not item_id:
            return Response(
                {'detail': 'No se ha enviado ningún elemento.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            nuevo_valor = ItemService.marcar_favorito(item_id=item_id, usuario=request.user)
            return Response({
                'detail': 'Favorito actualizado correctamente.',
                'favorito': nuevo_valor,
            })
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=inline_serializer('TrashRequest', fields={'ids': drf_serializers.ListField(child=drf_serializers.IntegerField())}),
        responses=inline_serializer('TrashResponse', fields={'detail': drf_serializers.CharField()}),
    )
    @action(detail=False, methods=['post'])
    def trash(self, request):
        ids = request.data.get('ids', [])
        if not ids:
            return Response(
                {'detail': 'No se han enviado elementos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            cantidad = ItemService.mover_a_papelera(ids=ids, usuario=request.user)
            return Response({'detail': f'Se han movido {cantidad} elementos a la papelera.'})
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=inline_serializer('EliminarDefinitivoRequest', fields={'ids': drf_serializers.ListField(child=drf_serializers.IntegerField())}),
        responses=inline_serializer('EliminarDefinitivoResponse', fields={
            'detail': drf_serializers.CharField(),
            'deleted_count': drf_serializers.IntegerField(),
            's3_keys_deleted': drf_serializers.IntegerField(),
        }),
    )
    @action(detail=False, methods=['delete'])
    def eliminar_definitivo(self, request):
        ids = request.data.get('ids', [])
        if not ids:
            return Response(
                {'detail': 'No se han enviado elementos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        all_ids = ItemService.recolectar_descendientes_id(ids, request.user)
        ids_archivos = list(
            Item.objects.filter(
                id__in=all_ids,
                usuario=request.user,
                tipo=Item.Tipo.ARCHIVO,
                eliminado=True,
            ).values_list('id', flat=True)
        )

        try:
            result = ItemService.eliminar_items_fisicos(
                ids=ids,
                usuario=request.user,
                bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
            )
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        for item_id in ids_archivos:
            ItemService.eliminar_del_indice(item_id)

        return Response({
            'detail': f"Se han eliminado {result['deleted_count']} elementos permanentemente.",
            'deleted_count': result['deleted_count'],
            's3_keys_deleted': result['s3_keys_deleted'],
        })

    @extend_schema(
        request=inline_serializer('RestaurarRequest', fields={'ids': drf_serializers.ListField(child=drf_serializers.IntegerField())}),
        responses=inline_serializer('RestaurarResponse', fields={'detail': drf_serializers.CharField()}),
    )
    @action(detail=False, methods=['post'])
    def restaurar(self, request):
        ids = request.data.get('ids', [])
        if not ids:
            return Response(
                {'detail': 'No se han enviado elementos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            restaurados = ItemService.restaurar_items(ids=ids, usuario=request.user)
            return Response({'detail': f'Se han restaurado {restaurados} elementos.'})
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=inline_serializer('MoverRequest', fields={
            'ids': drf_serializers.ListField(child=drf_serializers.IntegerField()),
            'destino': drf_serializers.IntegerField(allow_null=True),
        }),
        responses=inline_serializer('MoverResponse', fields={'detail': drf_serializers.CharField()}),
    )
    @action(detail=False, methods=['post'])
    def mover(self, request):
        ids = request.data.get('ids', [])
        destino_id = request.data.get('destino', None)

        if not ids:
            return Response(
                {'detail': 'No se han enviado elementos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        destino = None
        if destino_id:
            try:
                destino = Item.objects.get(
                    id=destino_id, usuario=request.user, tipo='carpeta', eliminado=False
                )
            except Item.DoesNotExist:
                return Response(
                    {'detail': 'Carpeta destino no encontrada.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        items_obj = list(Item.objects.filter(id__in=ids, usuario=request.user, eliminado=False))
        try:
            for item in items_obj:
                ItemService.mover_item(item, destino)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'detail': f'Se han movido {len(items_obj)} elementos.'})

    @extend_schema(
        request=None,
        responses=inline_serializer('RestaurarPapeleraResponse', fields={'detail': drf_serializers.CharField()}),
    )
    @action(detail=False, methods=['post'])
    def restaurar_papelera(self, request):
        ids = list(
            Item.objects.filter(
                usuario=request.user,
                eliminado=True,
            ).values_list('id', flat=True)
        )
        try:
            restaurados = ItemService.restaurar_items(ids=ids, usuario=request.user)
            return Response({'detail': f'Se han restaurado {restaurados} elementos.'})
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=None,
        responses=inline_serializer('VaciarPapeleraResponse', fields={
            'detail': drf_serializers.CharField(),
            'deleted_count': drf_serializers.IntegerField(),
            's3_keys_deleted': drf_serializers.IntegerField(),
        }),
    )
    @action(detail=False, methods=['post'])
    def vaciar_papelera(self, request):
        ids_archivos = list(
            Item.objects.filter(
                usuario=request.user,
                eliminado=True,
                tipo=Item.Tipo.ARCHIVO,
            ).values_list('id', flat=True)
        )

        try:
            result = ItemService.vaciar_papelera(
                usuario=request.user,
                bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
            )
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        for item_id in ids_archivos:
            ItemService.eliminar_del_indice(item_id)

        return Response({
            'detail': 'Papelera vaciada correctamente.',
            'deleted_count': result['deleted_count'],
            's3_keys_deleted': result['s3_keys_deleted'],
        })

    # =========================================================
    # DESCARGA
    # =========================================================

    # Presigned URL de descarga directa para un archivo
    @extend_schema(
        responses=inline_serializer('DescargaArchivoResponse', fields={'url': drf_serializers.URLField()}),
    )
    @action(detail=True, methods=['get'])
    def descargar_archivo(self, request, pk=None):
        item = self.get_object()
        if item.tipo != 'archivo' or not item.file:
            return Response(
                {'detail': 'El elemento no es un archivo descargable.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'url': ItemService.generar_url_descarga(item)})

    # Presigned URL inline para previsualizar imagen, audio o PDF.

    @extend_schema(
        responses={
            200: inline_serializer('PreviewResponse', fields={'url': drf_serializers.URLField()}),
            400: inline_serializer('PreviewNoDisponible', fields={'detail': drf_serializers.CharField()}),
            409: inline_serializer('PreviewGenerandose', fields={'detail': drf_serializers.CharField()}),
        },
    )
    @action(detail=True, methods=['get'])
    def previsualizar(self, request, pk=None):
        item = self.get_object()
        if item.tipo != 'archivo' or not item.file:
            return Response(
                {'detail': 'El elemento no es un archivo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if mime_previsualizable(item.mime_type) is not None:
            return Response({'url': ItemService.generar_url_preview(item)})


        if mime_con_preview_generada(item.mime_type):
            if item.preview_key == PREVIEW_FALLIDA:
                return Response(
                    {'detail': 'No se ha podido generar la vista previa de este archivo.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not item.preview_key:
                return Response(
                    {'detail': 'La vista previa todavía se está generando.'},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response({'url': ItemService.generar_url_preview_generada(item)})

        return Response(
            {'detail': 'Tipo de archivo no previsualizable.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @extend_schema(
        request=inline_serializer('DescargarZipRequest', fields={'ids': drf_serializers.ListField(child=drf_serializers.IntegerField())}),
        responses={(200, 'application/zip'): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=['post'])
    def descargar(self, request):
        ids = request.data.get('ids', [])
        if not ids:
            return Response(
                {'detail': 'No se han enviado elementos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        archivos_con_ruta = ItemService.recolectar_archivos_para_zip(
            root_ids=ids,
            usuario=request.user,
        )

        if not archivos_con_ruta:
            return Response(
                {'detail': 'No se encontraron archivos para descargar.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        response = StreamingHttpResponse(
            ItemService.stream_zip(archivos_con_ruta, settings.AWS_STORAGE_BUCKET_NAME),
            content_type='application/zip',
        )
        response['Content-Disposition'] = 'attachment; filename="descarga.zip"'
        return response


    # =========================================================
    # VERSIONES (solo audio)
    # =========================================================

    @extend_schema(
        responses=inline_serializer('VersionesListarResponse', fields={
            'versiones': ItemVersionSerializer(many=True),
            'numero_actual': drf_serializers.IntegerField(),
        }),
    )
    @action(detail=True, methods=['get'], url_path='versiones', url_name='versiones-listar')
    def versiones_listar(self, request, pk=None):
        item = self.get_object()
        versiones = ItemService.listar_versiones(item)
        serializer = ItemVersionSerializer(versiones, many=True)
        version_activa = item.versiones.filter(es_actual=True).first()
        numero_actual = version_activa.numero if version_activa else item.versiones.count() + 1
        return Response({'versiones': serializer.data, 'numero_actual': numero_actual})

    @extend_schema(
        request=None,
        responses=inline_serializer('VersionesSolicitarSubidaResponse', fields={
            'url_subida': drf_serializers.URLField(),
            'key': drf_serializers.CharField(),
        }),
    )
    @action(detail=True, methods=['post'], url_path='versiones/solicitar_subida', url_name='versiones-solicitar')
    def versiones_solicitar_subida(self, request, pk=None):
        item = self.get_object()
        if item.tipo != Item.Tipo.ARCHIVO or not (item.mime_type or '').startswith('audio/'):
            return Response(
                {'detail': 'El control de versiones solo está disponible para archivos de audio.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        url_subida, key = ItemService.generar_url_presignada_version(item)
        return Response({'url_subida': url_subida, 'key': key})

    @extend_schema(
        request=inline_serializer('VersionesConfirmarSubidaRequest', fields={
            'key': drf_serializers.CharField(),
            'tamano_bytes': drf_serializers.IntegerField(required=False),
            'mime_type': drf_serializers.CharField(required=False),
        }),
        responses=ItemSerializer,
    )
    @action(detail=True, methods=['post'], url_path='versiones/confirmar_subida', url_name='versiones-confirmar')
    def versiones_confirmar_subida(self, request, pk=None):
        item       = self.get_object()
        key        = request.data.get('key', '').strip()
        mime_type  = request.data.get('mime_type', '')
        if not key:
            return Response({'detail': 'key es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)
        # Las versiones son solo de audio: no permitimos convertir un audio en
        # HTML/SVG declarando otro mime_type al confirmar.
        if not (mime_type or '').split(';')[0].strip().lower().startswith('audio/'):
            return Response(
                {'detail': 'El control de versiones solo acepta archivos de audio.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tamano = ItemService.validar_key_subida(request.user, key, subcarpeta='v/')
        item = ItemService.registrar_version(item, key, tamano, mime_type)
        threading.Thread(target=ItemService.indexar_item, args=(item,), daemon=True).start()
        return Response(ItemSerializer(item, context={'request': request}).data)

    @extend_schema(
        responses=inline_serializer('VersionesDescargarResponse', fields={'url': drf_serializers.URLField()}),
    )
    @action(detail=True, methods=['get'], url_path=r'versiones/(?P<num>[0-9]+)/descargar', url_name='versiones-descargar')
    def versiones_descargar(self, request, pk=None, num=None):
        item = self.get_object()
        try:
            version = item.versiones.get(numero=int(num))
        except ItemVersion.DoesNotExist:
            return Response({'detail': 'Versión no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        url = ItemService.generar_url_descarga_version(version, item.nombre)
        return Response({'url': url})

    @extend_schema(request=None, responses=ItemSerializer)
    @action(detail=True, methods=['post'], url_path=r'versiones/(?P<num>[0-9]+)/activar', url_name='versiones-activar')
    def versiones_activar(self, request, pk=None, num=None):
        item = self.get_object()
        try:
            version = item.versiones.get(numero=int(num))
        except ItemVersion.DoesNotExist:
            return Response({'detail': 'Versión no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            item = ItemService.activar_version(item, version)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        threading.Thread(target=ItemService.indexar_item, args=(item,), daemon=True).start()
        return Response(ItemSerializer(item, context={'request': request}).data)

    @extend_schema(
        responses=inline_serializer('VersionesPreviewResponse', fields={'url': drf_serializers.URLField()}),
    )
    @action(detail=True, methods=['get'], url_path=r'versiones/(?P<num>[0-9]+)/previsualizar', url_name='versiones-previsualizar')
    def versiones_previsualizar(self, request, pk=None, num=None):
        item = self.get_object()
        try:
            version = item.versiones.get(numero=int(num))
        except ItemVersion.DoesNotExist:
            return Response({'detail': 'Versión no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        if mime_previsualizable(version.mime_type) is None:
            return Response(
                {'detail': 'Tipo de archivo no previsualizable.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        url = ItemService.generar_url_preview_version(version)
        return Response({'url': url})

    @extend_schema(responses={204: None})
    @action(detail=True, methods=['delete'], url_path=r'versiones/(?P<num>[0-9]+)', url_name='versiones-eliminar')
    def versiones_eliminar(self, request, pk=None, num=None):
        item = self.get_object()
        try:
            version = item.versiones.get(numero=int(num))
        except ItemVersion.DoesNotExist:
            return Response({'detail': 'Versión no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        if version.es_actual:
            return Response(
                {'detail': 'No puedes eliminar la versión activa. Marca otra como actual primero.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ItemService.eliminar_version(version, settings.AWS_STORAGE_BUCKET_NAME)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # =========================================================
    # BÚSQUEDA
    # =========================================================

    @extend_schema(
        parameters=[OpenApiParameter('q', OpenApiTypes.STR, required=True, description='Texto de búsqueda')],
        responses=inline_serializer('BuscarResponse', fields={
            'items': ItemSerializer(many=True),
            'query': drf_serializers.CharField(),
        }),
    )
    @action(detail=False, methods=['get'])
    def buscar(self, request):
        q = request.query_params.get('q', '').strip()
        if not q:
            return Response(
                {'detail': 'El parámetro q es obligatorio.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            resultados = ItemService.buscar_items(usuario=request.user, q=q)
        except Exception:
            return Response(
                {'detail': 'Error al conectar con el motor de búsqueda.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        serializer = self.get_serializer(resultados, many=True)
        return Response({'items': serializer.data, 'query': q})

    # =========================================================
    # SUBIDA PRESIGNADA (De Vue a Garage directo)
    # =========================================================

    @extend_schema(
        request=inline_serializer('SolicitarSubidaRequest', fields={
            'nombre': drf_serializers.CharField(),
            'mime_type': drf_serializers.CharField(required=False),
        }),
        responses=inline_serializer('SolicitarSubidaResponse', fields={
            'url_subida': drf_serializers.URLField(),
            'key': drf_serializers.CharField(),
        }),
    )
    @action(detail=False, methods=['post'])
    def solicitar_subida(self, request):
        nombre = request.data.get('nombre', '').strip()
        mime_type = request.data.get('mime_type', 'application/octet-stream')

        if not nombre:
            return Response({'detail': 'El nombre es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)

        _, extension = os.path.splitext(nombre)
        key = f"users/{request.user.id}/{uuid.uuid4().hex}{extension}"

        url_subida = ItemService.generar_url_presignada_subida(key)
        return Response({'url_subida': url_subida, 'key': key})

    @extend_schema(
        request=inline_serializer('ConfirmarSubidaRequest', fields={
            'nombre': drf_serializers.CharField(),
            'key': drf_serializers.CharField(),
            'padre': drf_serializers.IntegerField(required=False, allow_null=True),
            'tamano_bytes': drf_serializers.IntegerField(required=False),
            'mime_type': drf_serializers.CharField(required=False),
        }),
        responses={201: ItemSerializer},
    )
    @action(detail=False, methods=['post'])
    def confirmar_subida(self, request):
        nombre = request.data.get('nombre', '').strip()
        key = request.data.get('key', '').strip()
        padre_id = request.data.get('padre', None)
        mime_type = request.data.get('mime_type', 'application/octet-stream')

        if not nombre or not key:
            return Response({'detail': 'nombre y key son obligatorios.'}, status=status.HTTP_400_BAD_REQUEST)

        tamano_bytes = ItemService.validar_key_subida(request.user, key)

        padre = None
        if padre_id:
            try:
                padre = Item.objects.get(id=padre_id, usuario=request.user, tipo='carpeta', eliminado=False)
            except Item.DoesNotExist:
                return Response({'detail': 'Carpeta padre no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            item = ItemService.registrar_item_subido(
                usuario=request.user,
                nombre=nombre,
                padre=padre,
                key=key,
                tamano_bytes=tamano_bytes,
                mime_type=mime_type,
            )
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        threading.Thread(target=ItemService.procesar_item_subido, args=(item,), daemon=True).start()

        serializer = self.get_serializer(item)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=inline_serializer('CrearArbolCarpetasRequest', fields={
            'rutas': drf_serializers.ListField(child=drf_serializers.CharField()),
            'padre': drf_serializers.IntegerField(required=False, allow_null=True),
        }),
        responses=inline_serializer('CrearArbolCarpetasResponse', fields={
            'mapa': drf_serializers.DictField(child=drf_serializers.IntegerField()),
        }),
    )
    @action(detail=False, methods=['post'])
    def crear_arbol_carpetas(self, request):
        rutas = request.data.get('rutas', [])
        padre_id = request.data.get('padre', None)
        
        if not rutas:
            return Response({'mapa': {}})
        
        mapa = {}
        
        padre_raiz = None
        if padre_id:
            try:
                padre_raiz = Item.objects.get(id=padre_id, usuario=request.user, tipo='carpeta', eliminado=False)
            except Item.DoesNotExist:
                return Response({'detail': 'Carpeta padre no encontrada.'}, status=404)
        
        try:
            with transaction.atomic():
                for ruta in rutas:
                    partes = ruta.split('/')
                    nombre = partes[-1]
                    
                    # El padre de esta carpeta es la ruta padre dentro del mapa
                    if len(partes) == 1:
                        padre = padre_raiz
                    else:
                        ruta_padre = '/'.join(partes[:-1])
                        padre_id_local = mapa.get(ruta_padre)
                        if padre_id_local is None:
                            return Response(
                                {'detail': f'Ruta padre no encontrada: {ruta_padre}'},
                                status=400
                            )
                        padre = Item.objects.get(id=padre_id_local)
                    
                    item = Item(
                        usuario=request.user,
                        nombre=nombre,
                        tipo=Item.Tipo.CARPETA,
                        padre=padre,
                    )
                    ItemService.guardar_item(item)
                    mapa[ruta] = item.id
                    
        except Exception as e:
            return Response({'detail': str(e)}, status=400)
        
        return Response({'mapa': mapa})
