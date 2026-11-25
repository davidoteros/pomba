import io
import threading
import time
from datetime import timedelta
from io import StringIO
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from botocore.exceptions import EndpointConnectionError
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from django_elasticsearch_dsl.registries import registry
from rest_framework.test import APIClient

from items.extractors import extraer
from items.models import Item, SubidaPendiente
from items.serializers import ConfirmarSubidaSerializer, SolicitarSubidaSerializer, VersionConfirmarSubidaSerializer
from items.services import BorradoGarageFallido, CuotaExcedida, ItemService

Usuario = get_user_model()


# Garage y Elasticsearch son los de desarrollo: se sustituyen por falsos para no tocar datos reales
@mock.patch.object(registry, 'delete_related')
@mock.patch.object(registry, 'update_related')
@mock.patch.object(registry, 'update')
@mock.patch.object(registry, 'delete')
@mock.patch('items.services.ItemService.get_s3_client')
class LimpiarSubidasTests(TestCase):
    """El comando limpiar_subidas borra los ficheros de subidas abandonadas y busca huérfanos."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(email='limpiar@prueba.com', password='Prueba1234!')

    def pase(self, key, minutos, item=None):
        SubidaPendiente.objects.create(key=key, usuario=self.usuario, item=item, tamano_declarado=1)
        # fecha_creacion es auto_now_add: se retrasa después de crearla
        SubidaPendiente.objects.filter(key=key).update(
            fecha_creacion=timezone.now() - timedelta(minutes=minutos),
        )

    def archivo(self, key, **extra):
        return Item.objects.create(
            usuario=self.usuario, nombre=key, tipo=Item.Tipo.ARCHIVO, file=key, **extra,
        )

    def claves_borradas(self, s3):
        llamadas = s3.return_value.delete_objects.call_args_list
        return {o['Key'] for c in llamadas for o in c.kwargs['Delete']['Objects']}

    def objeto(self, key, dias):
        return {'Key': key, 'Size': 10, 'LastModified': timezone.now() - timedelta(days=dias)}

    def bucket(self, s3, *objetos):
        s3.return_value.get_paginator.return_value.paginate.return_value = [{'Contents': list(objetos)}]

    def ejecutar(self, *args):
        salida = StringIO()
        call_command('limpiar_subidas', *args, stdout=salida)
        return salida.getvalue()

    def test_borra_caducadas_y_respeta_vivas_y_margen(self, s3, *_):
        s3.return_value.delete_objects.return_value = {}
        self.pase('files/vieja.bin', 80)
        self.pase('files/margen.bin', 65)  # caducada, pero dentro del margen de 10 min
        self.pase('files/viva.bin', 5)
        self.ejecutar()
        self.assertEqual(self.claves_borradas(s3), {'files/vieja.bin'})
        self.assertEqual(
            set(SubidaPendiente.objects.values_list('key', flat=True)),
            {'files/margen.bin', 'files/viva.bin'},
        )

    def test_no_borra_un_fichero_que_ya_es_de_un_item(self, s3, *_):
        self.archivo('files/confirmado.bin')
        self.pase('files/confirmado.bin', 80)
        self.ejecutar()
        s3.return_value.delete_objects.assert_not_called()
        self.assertFalse(SubidaPendiente.objects.exists())

    def test_si_garage_falla_los_pases_se_quedan(self, s3, *_):
        s3.return_value.delete_objects.return_value = {
            'Errors': [{'Key': 'files/vieja.bin', 'Code': 'InternalError'}],
        }
        self.pase('files/vieja.bin', 80)
        with self.assertRaises(BorradoGarageFallido):
            self.ejecutar()
        self.assertTrue(SubidaPendiente.objects.filter(key='files/vieja.bin').exists())

    def preparar_bucket(self, s3):
        self.archivo('files/registrado.txt')
        self.archivo('files/roto.txt')
        self.pase('files/pase.bin', 5)
        self.bucket(
            s3,
            self.objeto('files/registrado.txt', 3),
            self.objeto('files/huerfano.bin', 3),
            self.objeto('files/reciente.bin', 0),  # puede ser una subida en curso
            self.objeto('files/pase.bin', 3),
        )

    def test_barrer_solo_lista(self, s3, *_):
        self.preparar_bucket(s3)
        salida = self.ejecutar('--barrer')
        self.assertIn('Huérfanos en Garage: 1 (10 bytes)', salida)
        self.assertIn('files/huerfano.bin', salida)
        self.assertIn('Rotos (en la BD pero no en Garage): 1', salida)
        self.assertIn('files/roto.txt', salida)
        s3.return_value.delete_objects.assert_not_called()

    def test_barrer_y_borrar_solo_borra_huerfanos(self, s3, *_):
        s3.return_value.delete_objects.return_value = {}
        self.preparar_bucket(s3)
        self.ejecutar('--barrer', '--borrar')
        self.assertEqual(self.claves_borradas(s3), {'files/huerfano.bin'})

    def test_borrar_sin_barrer_falla(self, s3, *_):
        with self.assertRaises(CommandError):
            self.ejecutar('--borrar')
        s3.return_value.delete_objects.assert_not_called()

    def test_vaciar_papelera_borra_la_version_que_se_estaba_subiendo(self, s3, *_):
        s3.return_value.delete_objects.return_value = {}
        audio = self.archivo('files/audio.mp3', eliminado=True)
        self.pase('files/v/nueva.mp3', 5, item=audio)
        ItemService.eliminar_items_fisicos([audio.pk], self.usuario, 'bucket')
        self.assertEqual(self.claves_borradas(s3), {'files/audio.mp3', 'files/v/nueva.mp3'})


def a_la_vez(n, funcion):
    """Lanza `funcion` en n hilos a la vez y devuelve lo que devuelve cada uno."""
    resultados = []

    def hilo():
        try:
            resultados.append(funcion())
        finally:
            connection.close()  # cada hilo abre su propia conexión a Postgres

    hilos = [threading.Thread(target=hilo) for _ in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    return resultados


# TransactionTestCase: con TestCase todo va en una sola transacción y la carrera no se puede ver
@mock.patch.object(registry, 'delete_related')
@mock.patch.object(registry, 'update_related')
@mock.patch.object(registry, 'update')
@mock.patch.object(registry, 'delete')
@mock.patch('items.services.ItemService.get_s3_client')
class CarreraCuotaTests(TransactionTestCase):
    """Peticiones simultáneas del mismo usuario no pueden pasarse de la cuota ni registrar dos veces una key."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(email='carrera@prueba.com', password='Prueba1234!')

    @override_settings(CUOTA_USUARIO_BYTES=300, LIMITE_FICHERO_BYTES=100)
    @mock.patch('items.services.ItemService.generar_url_presignada_subida', return_value='url')
    def test_pases_simultaneos_no_pasan_de_la_cuota(self, _url, *_):
        original = ItemService.espacio_usado

        def lento(usuario):
            time.sleep(0.2)  # ensancha la ventana para que la carrera salga siempre
            return original(usuario)

        def pedir():
            try:
                ItemService.entregar_pase_subida(self.usuario, 'f.bin', 100)
                return 'pase'
            except CuotaExcedida:
                return 'sin sitio'

        with mock.patch.object(ItemService, 'espacio_usado', side_effect=lento):
            resultados = a_la_vez(5, pedir)

        self.assertEqual(resultados.count('pase'), 3)
        self.assertEqual(SubidaPendiente.objects.count(), 3)

    @mock.patch('items.services.ItemService.procesar_item_subido')
    def test_confirmar_dos_veces_la_misma_key_crea_un_solo_item(self, _procesar, s3, *_):
        SubidaPendiente.objects.create(key='files/doble.bin', usuario=self.usuario, tamano_declarado=10)

        def head_lento(**_):
            time.sleep(0.2)  # las dos peticiones pasan el head_object antes de consumir el pase
            return {'ContentLength': 10}

        s3.return_value.head_object.side_effect = head_lento

        def confirmar():
            cliente = APIClient()
            cliente.force_authenticate(self.usuario)
            return cliente.post(
                '/api/items/confirmar_subida/', {'nombre': 'doble.bin', 'key': 'files/doble.bin'}, format='json',
            ).status_code

        self.assertEqual(sorted(a_la_vez(2, confirmar)), [201, 400])
        self.assertEqual(Item.objects.filter(file='files/doble.bin').count(), 1)


GARAGE_CAIDO = EndpointConnectionError(endpoint_url='http://garage:3900/pomba-app?delete')


@mock.patch.object(registry, 'delete_related')
@mock.patch.object(registry, 'update_related')
@mock.patch.object(registry, 'update')
@mock.patch.object(registry, 'delete')
@mock.patch('items.services.ItemService.get_s3_client')
class ErroresTests(TestCase):
    """Los errores internos van al log y el cliente solo recibe mensajes escritos para él."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(email='errores@prueba.com', password='Prueba1234!')
        # Que devuelva la respuesta del 5xx en vez de relanzar el error en la prueba
        self.cliente = APIClient(raise_request_exception=False)
        self.cliente.force_authenticate(self.usuario)

    def carpeta(self, nombre, padre=None, usuario=None):
        return Item.objects.create(
            usuario=usuario or self.usuario, nombre=nombre, tipo=Item.Tipo.CARPETA, padre=padre,
        )

    def primer_error(self, respuesta):
        return respuesta.json()['errors'][0]

    def test_garage_caido_al_vaciar_papelera_da_503_sin_detalles(self, s3, *_):
        Item.objects.create(
            usuario=self.usuario, nombre='f.txt', tipo=Item.Tipo.ARCHIVO, file='files/f.txt', eliminado=True,
        )
        s3.return_value.delete_objects.side_effect = GARAGE_CAIDO

        with self.assertLogs('django.request', 'ERROR') as log:
            respuesta = self.cliente.post('/api/items/vaciar_papelera/')

        self.assertEqual(respuesta.status_code, 503)
        self.assertNotIn('garage', respuesta.content.decode())
        self.assertIn('garage:3900', str(log.records[0].exc_info[1]))
        self.assertTrue(Item.objects.filter(file='files/f.txt').exists())

    def test_error_inesperado_da_500_generico_y_queda_en_el_log(self, *_):
        item = self.carpeta('A')
        item.eliminado = True
        item.save()

        with mock.patch.object(ItemService, 'restaurar_items', side_effect=RuntimeError('secreto')):
            with self.assertLogs('django.request', 'ERROR') as log:
                respuesta = self.cliente.post('/api/items/restaurar/', {'ids': [item.id]}, format='json')

        self.assertEqual(respuesta.status_code, 500)
        self.assertNotIn('secreto', respuesta.content.decode())
        self.assertIn('secreto', str(log.records[0].exc_info[1]))

    def test_mover_dentro_de_su_hija_da_400_con_mensaje_limpio(self, *_):
        a = self.carpeta('A')
        b = self.carpeta('B', padre=a)

        respuesta = self.cliente.post('/api/items/mover/', {'ids': [a.id], 'destino': b.id}, format='json')

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(self.primer_error(respuesta)['detail'], 'No puedes crear ciclos')

    def test_renombrar_con_nombre_largo_da_400_en_el_campo_nombre(self, *_):
        a = self.carpeta('A')

        respuesta = self.cliente.post(f'/api/items/{a.id}/renombrar/', {'nombre': 'x' * 300}, format='json')

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(self.primer_error(respuesta)['attr'], 'nombre')
        self.assertNotIn('ErrorDetail', respuesta.content.decode())

    def test_favorito_de_otro_usuario_da_404(self, *_):
        otro = Usuario.objects.create_user(email='otro@prueba.com', password='Prueba1234!')
        ajena = self.carpeta('ajena', usuario=otro)

        respuesta = self.cliente.post('/api/items/favorito/', {'id': ajena.id}, format='json')

        self.assertEqual(respuesta.status_code, 404)

    def test_arbol_con_ruta_padre_que_falta_no_deja_carpetas_a_medias(self, *_):
        respuesta = self.cliente.post(
            '/api/items/crear_arbol_carpetas/', {'rutas': ['a', 'x/b']}, format='json',
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(Item.objects.filter(usuario=self.usuario).exists())

    def test_garage_caido_al_confirmar_da_503_y_el_pase_se_queda(self, s3, *_):
        SubidaPendiente.objects.create(key='files/c.txt', usuario=self.usuario, tamano_declarado=10)
        s3.return_value.head_object.side_effect = GARAGE_CAIDO

        with self.assertLogs('django.request', 'ERROR'):
            respuesta = self.cliente.post(
                '/api/items/confirmar_subida/', {'nombre': 'c.txt', 'key': 'files/c.txt'}, format='json',
            )

        self.assertEqual(respuesta.status_code, 503)
        self.assertNotIn('garage', respuesta.content.decode())
        self.assertTrue(SubidaPendiente.objects.filter(key='files/c.txt').exists())

    def test_los_5xx_llevan_la_referencia_de_nginx_en_la_respuesta_y_en_el_log(self, s3, *_):
        ref = 'a1b2c3d4e5f60718293a4b5c6d7e8f90'
        Item.objects.create(
            usuario=self.usuario, nombre='f.txt', tipo=Item.Tipo.ARCHIVO, file='files/f.txt', eliminado=True,
        )
        s3.return_value.delete_objects.side_effect = GARAGE_CAIDO

        with self.assertLogs('django.request', 'ERROR') as log:
            respuesta = self.cliente.post('/api/items/vaciar_papelera/', HTTP_X_REQUEST_ID=ref)

        self.assertEqual(respuesta.status_code, 503)
        self.assertIn(f'(ref. {ref})', self.primer_error(respuesta)['detail'])
        self.assertIn(ref, log.output[0])

    def test_el_500_generico_tambien_lleva_la_referencia(self, *_):
        ref = '0123456789abcdef0123456789abcdef'
        with mock.patch.object(ItemService, 'restaurar_items', side_effect=RuntimeError('secreto')):
            with self.assertLogs('django.request', 'ERROR') as log:
                respuesta = self.cliente.post(
                    '/api/items/restaurar/', {'ids': [1]}, format='json', HTTP_X_REQUEST_ID=ref,
                )

        self.assertEqual(respuesta.status_code, 500)
        self.assertEqual(self.primer_error(respuesta)['detail'], f'Se ha producido un error en el servidor. (ref. {ref})')
        self.assertIn(ref, log.output[0])

    def test_una_referencia_con_formato_raro_se_ignora(self, *_):
        with mock.patch.object(ItemService, 'restaurar_items', side_effect=RuntimeError('secreto')):
            with self.assertLogs('django.request', 'ERROR') as log:
                respuesta = self.cliente.post(
                    '/api/items/restaurar/', {'ids': [1]}, format='json',
                    HTTP_X_REQUEST_ID='falso\nERROR linea inventada',
                )

        self.assertEqual(self.primer_error(respuesta)['detail'], 'Se ha producido un error en el servidor.')
        self.assertNotIn('inventada', log.output[0])


@override_settings(CUOTA_USUARIO_BYTES=20 * 1024 ** 3, LIMITE_FICHERO_BYTES=2 * 1024 ** 3)
class MensajesCuotaTests(TestCase):
    """Los mensajes de cuota los lee el usuario: tamaños en MB/GB, no en bytes."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(email='cuota@prueba.com', password='Prueba1234!')

    def test_sin_espacio_dice_cuanto_queda_en_unidades_legibles(self):
        usado = 20 * 1024 ** 3 - 1024 ** 2
        with mock.patch.object(ItemService, 'espacio_usado', return_value=usado):
            with self.assertRaises(CuotaExcedida) as error:
                ItemService.comprobar_cuota(self.usuario, 2 * 1024 ** 2)
        self.assertEqual(error.exception.mensaje, 'Sin espacio: quedan 1,0\xa0MB libres de 20,0\xa0GB.')

    def test_fichero_demasiado_grande_dice_el_maximo_en_unidades_legibles(self):
        with self.assertRaises(CuotaExcedida) as error:
            ItemService.comprobar_cuota(self.usuario, 3 * 1024 ** 3)
        self.assertEqual(error.exception.mensaje, 'El archivo supera el máximo de 2,0\xa0GB por fichero.')


class LogInyeccionTests(SimpleTestCase):
    """Un dato del cliente con saltos de línea no puede partir una línea del log."""

    def test_mime_con_salto_de_linea_queda_en_una_linea(self):
        mime = 'image/png;\nCRITICAL users.views Login correcto del admin'
        with self.assertLogs('items.extractors', level='WARNING') as logs:
            extraer(b'esto no es un png', mime, 17)
        self.assertEqual(len(logs.records), 1)
        self.assertNotIn('\n', logs.records[0].getMessage())


@mock.patch.object(registry, 'delete_related')
@mock.patch.object(registry, 'update_related')
@mock.patch.object(registry, 'update')
@mock.patch.object(registry, 'delete')
@mock.patch('items.services.ItemService.get_s3_client')
class NombreItemTests(TestCase):
    """El nombre acaba como ruta en el ZIP y en la cabecera de descarga: sin barras, puntos sueltos ni control."""

    PROHIBIDOS = ['.', '..', 'a/b', '../../.bashrc', 'a\\b', 'a\nb', 'a\tb', 'a\x7fb']

    def setUp(self):
        self.usuario = Usuario.objects.create_user(email='nombres@prueba.com', password='Prueba1234!')
        self.cliente = APIClient()
        self.cliente.force_authenticate(self.usuario)

    def attr(self, respuesta):
        return respuesta.json()['errors'][0]['attr']

    def test_crear_carpeta_con_nombre_prohibido_da_400(self, *_):
        for nombre in self.PROHIBIDOS:
            with self.subTest(nombre=nombre):
                respuesta = self.cliente.post('/api/items/', {'nombre': nombre, 'tipo': 'carpeta'}, format='json')
                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(self.attr(respuesta), 'nombre')
        self.assertFalse(Item.objects.exists())

    def test_renombrar_con_ruta_da_400_y_no_cambia(self, *_):
        item = Item.objects.create(usuario=self.usuario, nombre='A', tipo=Item.Tipo.CARPETA)
        for nombre in self.PROHIBIDOS:
            with self.subTest(nombre=nombre):
                respuesta = self.cliente.post(f'/api/items/{item.id}/renombrar/', {'nombre': nombre}, format='json')
                self.assertEqual(respuesta.status_code, 400)
        item.refresh_from_db()
        self.assertEqual(item.nombre, 'A')

    def test_subir_con_nombre_prohibido_se_rechaza_antes_de_tocar_garage(self, *_):
        with mock.patch.object(ItemService, 'entregar_pase_subida') as pase:
            respuesta = self.cliente.post(
                '/api/items/solicitar_subida/', {'nombre': '../x.txt', 'tamano_bytes': 1}, format='json',
            )
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(self.attr(respuesta), 'nombre')
        pase.assert_not_called()

        with mock.patch.object(ItemService, 'validar_key_subida') as validar:
            respuesta = self.cliente.post(
                '/api/items/confirmar_subida/', {'nombre': 'a/b.txt', 'key': 'files/x.txt'}, format='json',
            )
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(self.attr(respuesta), 'nombre')
        validar.assert_not_called()

    def test_subir_carpeta_con_parte_prohibida_no_crea_nada(self, *_):
        respuesta = self.cliente.post(
            '/api/items/crear_arbol_carpetas/', {'rutas': ['A', 'A/..']}, format='json',
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(Item.objects.exists())

    def test_subir_carpeta_quita_los_espacios_de_los_extremos(self, *_):
        respuesta = self.cliente.post(
            '/api/items/crear_arbol_carpetas/', {'rutas': ['fotos ', 'fotos / viaje']}, format='json',
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(set(respuesta.json()['mapa']), {'fotos ', 'fotos / viaje'})
        self.assertEqual(sorted(Item.objects.values_list('nombre', flat=True)), ['fotos', 'viaje'])

    def test_cabecera_de_descarga_escapa_el_nombre(self, *_):
        item = Item(usuario=self.usuario, nombre='canción "x".mp3', tipo=Item.Tipo.ARCHIVO, file='files/x.mp3')
        version = mock.Mock(file='files/v/x.mp3')
        esperada = "attachment; filename*=utf-8''canci%C3%B3n%20%22x%22.mp3"
        for url in (ItemService.generar_url_descarga(item),
                    ItemService.generar_url_descarga_version(version, item.nombre)):
            cabecera = parse_qs(urlsplit(url).query)['response-content-disposition'][0]
            self.assertEqual(cabecera, esperada)


@mock.patch.object(registry, 'delete_related')
@mock.patch.object(registry, 'update_related')
@mock.patch.object(registry, 'update')
@mock.patch.object(registry, 'delete')
@mock.patch('items.services.ItemService.get_s3_client')
class EntradaAccionesTests(TestCase):
    """Las acciones solo aceptan datos con la forma esperada: lo demás es 400 antes de tocar nada."""

    IDS_MAL_FORMADOS = [
        {'ids': '15'}, {'ids': ['abc']}, {'ids': [None]}, {'ids': [0]}, {'ids': {'x': 1}},
        {'ids': []}, {}, {'ids': list(range(1, 10_002))},
    ]
    ID_MAL_FORMADOS = ['abc', 0, -1, [1], None, 1.5]

    def setUp(self):
        self.usuario = Usuario.objects.create_user(email='entrada@prueba.com', password='Prueba1234!')
        self.cliente = APIClient(raise_request_exception=False)
        self.cliente.force_authenticate(self.usuario)

    def item(self, nombre, tipo=Item.Tipo.CARPETA, **extra):
        return Item.objects.create(usuario=self.usuario, nombre=nombre, tipo=tipo, **extra)

    def comprobar_400(self, respuesta, campo):
        self.assertEqual(respuesta.status_code, 400)
        self.assertTrue(respuesta.json()['errors'][0]['attr'].startswith(campo))

    def test_acciones_en_lote_con_ids_mal_formados_dan_400_sin_tocar_nada(self, *_):
        acciones = [
            ('post', '/api/items/restaurar/', 'restaurar_items'),
            ('post', '/api/items/trash/', 'mover_a_papelera'),
            ('delete', '/api/items/eliminar_definitivo/', 'recolectar_descendientes_id'),
            ('post', '/api/items/descargar/', 'recolectar_archivos_para_zip'),
            ('post', '/api/items/mover/', 'mover_item'),
        ]
        for metodo, url, servicio in acciones:
            for cuerpo in self.IDS_MAL_FORMADOS:
                with self.subTest(url=url, cuerpo=str(cuerpo)[:30]):
                    with mock.patch.object(ItemService, servicio) as falso:
                        respuesta = getattr(self.cliente, metodo)(url, cuerpo, format='json')
                    self.comprobar_400(respuesta, 'ids')
                    falso.assert_not_called()

    def test_restaurar_con_ids_buenos_sigue_funcionando(self, *_):
        item = self.item('f.txt', Item.Tipo.ARCHIVO, file='files/f.txt', eliminado=True)
        respuesta = self.cliente.post('/api/items/restaurar/', {'ids': [item.id]}, format='json')
        self.assertEqual(respuesta.status_code, 200)
        item.refresh_from_db()
        self.assertFalse(item.eliminado)

    def test_favorito_con_id_mal_formado_da_400(self, *_):
        for valor in self.ID_MAL_FORMADOS:
            with self.subTest(id=valor):
                with mock.patch.object(ItemService, 'marcar_favorito', return_value=True) as falso:
                    respuesta = self.cliente.post('/api/items/favorito/', {'id': valor}, format='json')
                self.comprobar_400(respuesta, 'id')
                falso.assert_not_called()

    def test_favorito_con_id_bueno_sigue_funcionando(self, *_):
        item = self.item('A')
        respuesta = self.cliente.post('/api/items/favorito/', {'id': item.id}, format='json')
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()['favorito'])

    def test_mover_con_destino_mal_formado_da_400(self, *_):
        item = self.item('A')
        for valor in self.ID_MAL_FORMADOS[:-2] + ['15']:
            with self.subTest(destino=valor):
                with mock.patch.object(ItemService, 'mover_item') as falso:
                    respuesta = self.cliente.post(
                        '/api/items/mover/', {'ids': [item.id], 'destino': valor}, format='json',
                    )
                # "15" se lee como el número 15 (como en el resto de DRF), pero no es una carpeta suya
                self.comprobar_400(respuesta, 'destino')
                falso.assert_not_called()

    def test_mover_a_carpeta_y_a_la_raiz_sigue_funcionando(self, *_):
        a, b = self.item('A'), self.item('B')
        respuesta = self.cliente.post('/api/items/mover/', {'ids': [a.id], 'destino': b.id}, format='json')
        self.assertEqual(respuesta.status_code, 200)
        a.refresh_from_db()
        self.assertEqual(a.padre_id, b.id)
        respuesta = self.cliente.post('/api/items/mover/', {'ids': [a.id], 'destino': None}, format='json')
        self.assertEqual(respuesta.status_code, 200)
        a.refresh_from_db()
        self.assertIsNone(a.padre_id)

    def test_mover_con_nombre_repetido_lo_renombra(self, *_):
        destino = self.item('Destino')
        self.item('f.txt', Item.Tipo.ARCHIVO, file='files/1.txt', padre=destino)
        self.item('Fotos', padre=destino)
        archivo = self.item('f.txt', Item.Tipo.ARCHIVO, file='files/2.txt')
        carpeta = self.item('Fotos')
        respuesta = self.cliente.post(
            '/api/items/mover/', {'ids': [archivo.id, carpeta.id], 'destino': destino.id}, format='json',
        )
        self.assertEqual(respuesta.status_code, 200)
        archivo.refresh_from_db()
        carpeta.refresh_from_db()
        self.assertEqual((archivo.nombre, archivo.padre_id), ('f (1).txt', destino.id))
        self.assertEqual((carpeta.nombre, carpeta.padre_id), ('Fotos (1)', destino.id))

    def test_mover_a_su_misma_carpeta_no_cambia_el_nombre(self, *_):
        carpeta = self.item('Carpeta')
        archivo = self.item('f.txt', Item.Tipo.ARCHIVO, file='files/1.txt', padre=carpeta)
        respuesta = self.cliente.post(
            '/api/items/mover/', {'ids': [archivo.id], 'destino': carpeta.id}, format='json',
        )
        self.assertEqual(respuesta.status_code, 200)
        archivo.refresh_from_db()
        self.assertEqual(archivo.nombre, 'f.txt')

    def test_renombrar_con_nombre_mal_formado_da_400(self, *_):
        item = self.item('A')
        for cuerpo in [{}, {'nombre': ''}, {'nombre': '   '}, {'nombre': ['B']}, {'nombre': {'x': 1}}]:
            with self.subTest(cuerpo=cuerpo):
                respuesta = self.cliente.post(f'/api/items/{item.id}/renombrar/', cuerpo, format='json')
                self.comprobar_400(respuesta, 'nombre')
        item.refresh_from_db()
        self.assertEqual(item.nombre, 'A')

    def test_renombrar_quita_los_espacios_de_los_extremos(self, *_):
        item = self.item('A')
        respuesta = self.cliente.post(f'/api/items/{item.id}/renombrar/', {'nombre': '  Bien  '}, format='json')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['nombre'], 'Bien')

    def test_crear_arbol_con_datos_mal_formados_da_400_sin_crear_nada(self, *_):
        casos = [
            ({'rutas': 'A/B'}, 'rutas'), ({'rutas': [None]}, 'rutas'), ({'rutas': ['']}, 'rutas'),
            ({'rutas': [['A']]}, 'rutas'), ({}, 'rutas'), ({'rutas': ['A'], 'padre': 'abc'}, 'padre'),
            ({'rutas': ['A'], 'padre': 0}, 'padre'),
        ]
        for cuerpo, campo in casos:
            with self.subTest(cuerpo=cuerpo):
                respuesta = self.cliente.post('/api/items/crear_arbol_carpetas/', cuerpo, format='json')
                self.comprobar_400(respuesta, campo)
        self.assertFalse(Item.objects.exists())

    def test_crear_arbol_con_lista_vacia_devuelve_mapa_vacio(self, *_):
        respuesta = self.cliente.post('/api/items/crear_arbol_carpetas/', {'rutas': []}, format='json')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {'mapa': {}})

    def test_subida_con_mime_mal_formado_da_400_antes_del_pase(self, *_):
        for mime in ['image/png\nFALSO', 'png', 'image/', '/png', 'image/png/x', 'imagen/pñg', 'a b/c']:
            with self.subTest(mime=mime):
                with mock.patch.object(ItemService, 'entregar_pase_subida') as pase:
                    respuesta = self.cliente.post(
                        '/api/items/solicitar_subida/',
                        {'nombre': 'a.png', 'tamano_bytes': 1, 'mime_type': mime}, format='json',
                    )
                self.comprobar_400(respuesta, 'mime_type')
                pase.assert_not_called()

    def test_mime_bien_formado_se_acepta_en_los_tres_serializers(self, *_):
        for mime in ['image/png', 'application/vnd.ms-excel', 'image/svg+xml', 'text/plain; charset=utf-8']:
            with self.subTest(mime=mime):
                self.assertTrue(SolicitarSubidaSerializer(
                    data={'nombre': 'a', 'tamano_bytes': 1, 'mime_type': mime}).is_valid())
                self.assertTrue(ConfirmarSubidaSerializer(
                    data={'nombre': 'a', 'key': 'files/a', 'mime_type': mime}).is_valid())
        self.assertTrue(VersionConfirmarSubidaSerializer(data={'key': 'k', 'mime_type': 'audio/mpeg'}).is_valid())
        self.assertFalse(VersionConfirmarSubidaSerializer(data={'key': 'k', 'mime_type': 'audio/mpeg\nX'}).is_valid())


@mock.patch.object(registry, 'delete_related')
@mock.patch.object(registry, 'update_related')
@mock.patch.object(registry, 'update')
@mock.patch.object(registry, 'delete')
@mock.patch('items.services.ItemService.get_s3_client')
class CarpetaDelUsuarioTests(TestCase):
    """Crear, subir, subir carpeta y mover solo aceptan como destino una carpeta tuya fuera de la papelera."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(email='carpetas@prueba.com', password='Prueba1234!')
        otro = Usuario.objects.create_user(email='otro@prueba.com', password='Prueba1234!')
        self.cliente = APIClient(raise_request_exception=False)
        self.cliente.force_authenticate(self.usuario)
        self.buena = Item.objects.create(usuario=self.usuario, nombre='Buena', tipo=Item.Tipo.CARPETA)
        self.item = Item.objects.create(usuario=self.usuario, nombre='Suelta', tipo=Item.Tipo.CARPETA)
        self.no_validas = {
            'ajena': Item.objects.create(usuario=otro, nombre='Ajena', tipo=Item.Tipo.CARPETA),
            'papelera': Item.objects.create(
                usuario=self.usuario, nombre='Borrada', tipo=Item.Tipo.CARPETA, eliminado=True,
            ),
            'fichero': Item.objects.create(
                usuario=self.usuario, nombre='f.txt', tipo=Item.Tipo.ARCHIVO, file='files/f.txt',
            ),
        }

    def comprobar_rechazo(self, url, cuerpo, campo):
        respuesta = self.cliente.post(url, cuerpo, format='json')
        self.assertEqual(respuesta.status_code, 400)
        error = respuesta.json()['errors'][0]
        self.assertEqual((error['attr'], error['detail']), (campo, 'Carpeta no encontrada.'))

    def test_las_cuatro_acciones_rechazan_igual_una_carpeta_no_valida(self, *_):
        total = Item.objects.count()
        for motivo, carpeta in self.no_validas.items():
            with self.subTest(accion='crear carpeta', motivo=motivo):
                self.comprobar_rechazo(
                    '/api/items/', {'nombre': 'X', 'tipo': 'carpeta', 'padre': carpeta.id}, 'padre',
                )
            with self.subTest(accion='subir', motivo=motivo):
                with mock.patch.object(ItemService, 'validar_key_subida') as validar:
                    self.comprobar_rechazo(
                        '/api/items/confirmar_subida/',
                        {'nombre': 'a.txt', 'key': 'files/a.txt', 'padre': carpeta.id}, 'padre',
                    )
                validar.assert_not_called()
            with self.subTest(accion='subir carpeta', motivo=motivo):
                self.comprobar_rechazo(
                    '/api/items/crear_arbol_carpetas/', {'rutas': ['X'], 'padre': carpeta.id}, 'padre',
                )
            with self.subTest(accion='mover', motivo=motivo):
                self.comprobar_rechazo(
                    '/api/items/mover/', {'ids': [self.item.id], 'destino': carpeta.id}, 'destino',
                )
        self.assertEqual(Item.objects.count(), total)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.padre_id)

    def test_las_cuatro_acciones_aceptan_una_carpeta_tuya(self, *_):
        respuesta = self.cliente.post(
            '/api/items/', {'nombre': 'X', 'tipo': 'carpeta', 'padre': self.buena.id}, format='json',
        )
        self.assertEqual(respuesta.status_code, 201)
        respuesta = self.cliente.post(
            '/api/items/crear_arbol_carpetas/', {'rutas': ['Y'], 'padre': self.buena.id}, format='json',
        )
        self.assertEqual(respuesta.status_code, 200)
        respuesta = self.cliente.post(
            '/api/items/mover/', {'ids': [self.item.id], 'destino': self.buena.id}, format='json',
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            set(Item.objects.filter(padre=self.buena).values_list('nombre', flat=True)), {'X', 'Y', 'Suelta'},
        )
        # Al subir, que pase de la carpeta a validar la key ya demuestra que la aceptó
        sin_sitio = CuotaExcedida('Sin espacio', 'cuota')
        with mock.patch.object(ItemService, 'validar_key_subida', side_effect=sin_sitio) as validar:
            self.cliente.post(
                '/api/items/confirmar_subida/',
                {'nombre': 'a.txt', 'key': 'files/a.txt', 'padre': self.buena.id}, format='json',
            )
        validar.assert_called_once()


@mock.patch.object(registry, 'delete_related')
@mock.patch.object(registry, 'update_related')
@mock.patch.object(registry, 'update')
@mock.patch.object(registry, 'delete')
@mock.patch('items.services.ItemService.get_s3_client')
@override_settings(CUOTA_USUARIO_BYTES=1000, LIMITE_FICHERO_BYTES=500)
class EspacioTests(TestCase):
    """La barra de espacio lee la misma cifra con la que el servidor decide la cuota."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(email='espacio@prueba.com', password='Prueba1234!')
        self.cliente = APIClient()
        self.cliente.force_authenticate(self.usuario)

    def archivo(self, nombre, tamano, **extra):
        return Item.objects.create(
            usuario=self.usuario, nombre=nombre, tipo=Item.Tipo.ARCHIVO, file=f'files/{nombre}',
            tamano_bytes=tamano, **extra,
        )

    def test_cuenta_ficheros_papelera_versiones_y_subidas_en_curso(self, *_):
        self.archivo('a.txt', 100)
        self.archivo('b.txt', 50, eliminado=True)
        audio = self.archivo('c.mp3', 30)
        audio.versiones.create(numero=1, file='files/v/1.mp3', tamano_bytes=25, es_actual=False)
        SubidaPendiente.objects.create(key='files/d.txt', usuario=self.usuario, tamano_declarado=10)

        respuesta = self.cliente.get('/api/items/espacio/')

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {'ocupado': 215, 'libre': 785, 'cuota': 1000, 'limite_fichero': 500})

    def test_por_encima_de_la_cuota_el_libre_es_cero(self, *_):
        self.archivo('grande.bin', 1200)
        self.assertEqual(self.cliente.get('/api/items/espacio/').json()['libre'], 0)

    def test_la_barra_y_el_413_usan_la_misma_cifra(self, *_):
        self.archivo('a.txt', 900)
        SubidaPendiente.objects.create(key='files/b.txt', usuario=self.usuario, tamano_declarado=50)
        libre = self.cliente.get('/api/items/espacio/').json()['libre']
        ItemService.comprobar_cuota(self.usuario, libre)
        with self.assertRaises(CuotaExcedida):
            ItemService.comprobar_cuota(self.usuario, libre + 1)

    def test_sin_sesion_no_hay_espacio(self, *_):
        self.assertEqual(APIClient().get('/api/items/espacio/').status_code, 403)


@mock.patch.object(registry, 'delete_related')
@mock.patch.object(registry, 'update_related')
@mock.patch.object(registry, 'update')
@mock.patch.object(registry, 'delete')
@mock.patch('items.services.ItemService.get_s3_client')
class InterruptorVersionesTests(TestCase):
    """VERSIONES_AUDIO del .env enciende o apaga el control de versiones en el servidor y en la interfaz."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(email='versiones@prueba.com', password='Prueba1234!')
        self.cliente = APIClient()
        self.cliente.force_authenticate(self.usuario)
        self.audio = Item.objects.create(
            usuario=self.usuario, nombre='a.mp3', tipo=Item.Tipo.ARCHIVO, file='files/a.mp3',
            mime_type='audio/mpeg', tamano_bytes=10,
        )
        self.audio.versiones.create(numero=1, file='files/a.mp3', tamano_bytes=10, mime_type='audio/mpeg', es_actual=True)
        self.texto = Item.objects.create(
            usuario=self.usuario, nombre='t.txt', tipo=Item.Tipo.ARCHIVO, file='files/t.txt', mime_type='text/plain',
        )

    def admite(self):
        items = {i['nombre']: i for i in self.cliente.get('/api/items/').json()['items']}
        return items['a.mp3']['admite_versiones'], items['t.txt']['admite_versiones']

    @override_settings(VERSIONES_AUDIO=True)
    def test_encendido_solo_el_audio_admite_versiones(self, *_):
        self.assertEqual(self.admite(), (True, False))
        self.assertEqual(self.cliente.get(f'/api/items/{self.audio.id}/versiones/').status_code, 200)

    @override_settings(VERSIONES_AUDIO=False)
    def test_apagado_nada_admite_versiones_y_las_rutas_dan_404(self, *_):
        self.assertEqual(self.admite(), (False, False))
        base = f'/api/items/{self.audio.id}/versiones'
        rutas = [
            ('get', f'{base}/', None),
            ('post', f'{base}/solicitar_subida/', {'tamano_bytes': 5}),
            ('post', f'{base}/confirmar_subida/', {'key': 'files/v/x.mp3', 'mime_type': 'audio/mpeg'}),
            ('get', f'{base}/1/descargar/', None),
            ('post', f'{base}/1/activar/', None),
            ('get', f'{base}/1/previsualizar/', None),
            ('delete', f'{base}/1/', None),
        ]
        for metodo, url, cuerpo in rutas:
            with self.subTest(url=url):
                respuesta = getattr(self.cliente, metodo)(url, cuerpo, format='json')
                self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(self.audio.versiones.count(), 1)


@mock.patch('items.services.ItemService.procesar_copias')
@mock.patch.object(registry, 'delete_related')
@mock.patch.object(registry, 'update_related')
@mock.patch.object(registry, 'update')
@mock.patch.object(registry, 'delete')
@mock.patch('items.services.ItemService.get_s3_client')
@override_settings(CUOTA_USUARIO_BYTES=10_000, LIMITE_FICHERO_BYTES=500)
class CopiarTests(TestCase):
    """Copiar crea ficheros nuevos de verdad (no alias), con su propio objeto en Garage y dentro de la cuota."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(email='copiar@prueba.com', password='Prueba1234!')
        self.cliente = APIClient(raise_request_exception=False)
        self.cliente.force_authenticate(self.usuario)

    def carpeta(self, nombre, padre=None, **extra):
        return Item.objects.create(usuario=self.usuario, nombre=nombre, tipo=Item.Tipo.CARPETA, padre=padre, **extra)

    def archivo(self, nombre, padre=None, tamano=100, mime='text/plain', **extra):
        return Item.objects.create(
            usuario=self.usuario, nombre=nombre, tipo=Item.Tipo.ARCHIVO, padre=padre, file=f'files/{nombre}',
            tamano_bytes=tamano, mime_type=mime, **extra,
        )

    def copiar(self, ids, destino):
        destino = destino.id if destino else None
        return self.cliente.post('/api/items/copiar/', {'ids': ids, 'destino': destino}, format='json')

    def test_copia_un_archivo_con_objeto_propio(self, s3_cliente, *_):
        destino = self.carpeta('Destino')
        original = self.archivo('a.txt', metadatos={'lineas': 3})
        respuesta = self.copiar([original.id], destino)
        self.assertEqual(respuesta.status_code, 200)
        copia = Item.objects.get(padre=destino, nombre='a.txt')
        self.assertNotEqual(copia.id, original.id)
        self.assertNotEqual(str(copia.file), str(original.file))
        self.assertTrue(str(copia.file).startswith('files/') and str(copia.file).endswith('.txt'))
        self.assertEqual((copia.tamano_bytes, copia.mime_type, copia.metadatos), (100, 'text/plain', {'lineas': 3}))
        s3_cliente.return_value.copy_object.assert_called_once()
        llamada = s3_cliente.return_value.copy_object.call_args.kwargs
        self.assertEqual(llamada['CopySource']['Key'], 'files/a.txt')
        self.assertEqual(llamada['Key'], str(copia.file))
        original.refresh_from_db()
        self.assertIsNone(original.padre_id)

    def test_en_la_misma_carpeta_numera_el_nombre(self, *_):
        original = self.archivo('a.txt')
        self.assertEqual(self.copiar([original.id], None).status_code, 200)
        self.assertEqual(
            sorted(Item.objects.filter(padre=None).values_list('nombre', flat=True)), ['a (1).txt', 'a.txt'],
        )

    def test_copia_una_carpeta_entera_sin_la_papelera(self, s3_cliente, *_):
        fotos = self.carpeta('Fotos')
        viaje = self.carpeta('Viaje', fotos)
        self.archivo('uno.jpg', fotos)
        self.archivo('dos.jpg', viaje)
        self.archivo('borrada.jpg', fotos, eliminado=True)
        destino = self.carpeta('Destino')
        self.assertEqual(self.copiar([fotos.id], destino).status_code, 200)
        copia = Item.objects.get(padre=destino, nombre='Fotos')
        self.assertEqual(sorted(copia.hijos.values_list('nombre', flat=True)), ['Viaje', 'uno.jpg'])
        self.assertEqual(list(Item.objects.get(padre=copia, nombre='Viaje').hijos.values_list('nombre', flat=True)), ['dos.jpg'])
        self.assertEqual(s3_cliente.return_value.copy_object.call_count, 2)

    def test_una_carpeta_no_se_copia_dentro_de_si_misma(self, s3_cliente, *_):
        fotos = self.carpeta('Fotos')
        dentro = self.carpeta('Dentro', fotos)
        for destino in (fotos, dentro):
            with self.subTest(destino=destino.nombre):
                respuesta = self.copiar([fotos.id], destino)
                self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(Item.objects.count(), 2)
        s3_cliente.return_value.copy_object.assert_not_called()

    def test_sin_espacio_no_copia_nada(self, s3_cliente, *_):
        original = self.archivo('grande.bin', tamano=400)
        self.archivo('ocupa.bin', tamano=9_500)
        respuesta = self.copiar([original.id], None)
        self.assertEqual(respuesta.status_code, 413)
        self.assertEqual(respuesta.json()['motivo'], 'cuota')
        self.assertEqual(Item.objects.count(), 2)
        s3_cliente.return_value.copy_object.assert_not_called()

    def test_una_carpeta_mayor_que_el_limite_por_fichero_si_se_copia(self, *_):
        fotos = self.carpeta('Fotos')
        self.archivo('uno.jpg', fotos, tamano=400)
        self.archivo('dos.jpg', fotos, tamano=400)
        self.assertEqual(self.copiar([fotos.id], None).status_code, 200)

    def test_si_garage_falla_a_mitad_se_deshace_todo(self, s3_cliente, *_):
        self.archivo('uno.txt')
        self.archivo('dos.txt')
        ids = list(Item.objects.values_list('id', flat=True))
        s3 = s3_cliente.return_value
        s3.copy_object.side_effect = [None, EndpointConnectionError(endpoint_url='http://garage')]
        s3.delete_objects.return_value = {}
        respuesta = self.copiar(ids, None)
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(Item.objects.count(), 2)
        primera = s3.copy_object.call_args_list[0].kwargs['Key']
        borradas = [o['Key'] for o in s3.delete_objects.call_args.kwargs['Delete']['Objects']]
        self.assertEqual(borradas, [primera])

    def test_ids_ajenos_se_ignoran(self, s3_cliente, *_):
        otro = Usuario.objects.create_user(email='otro@prueba.com', password='Prueba1234!')
        ajeno = Item.objects.create(usuario=otro, nombre='x.txt', tipo=Item.Tipo.ARCHIVO, file='files/x.txt', tamano_bytes=1)
        self.assertEqual(self.copiar([ajeno.id], None).status_code, 200)
        self.assertFalse(Item.objects.filter(usuario=self.usuario).exists())
        s3_cliente.return_value.copy_object.assert_not_called()

    def test_un_audio_copiado_lleva_su_version_1(self, *_):
        audio = self.archivo('a.mp3', mime='audio/mpeg')
        audio.versiones.create(numero=1, file='files/a.mp3', tamano_bytes=100, mime_type='audio/mpeg', es_actual=True)
        audio.versiones.create(numero=2, file='files/v/b.mp3', tamano_bytes=50, mime_type='audio/mpeg', es_actual=False)
        self.assertEqual(self.copiar([audio.id], None).status_code, 200)
        copia = Item.objects.exclude(id=audio.id).get()
        self.assertEqual(list(copia.versiones.values_list('numero', 'file', 'es_actual')), [(1, str(copia.file), True)])

    def test_mas_de_1000_elementos_da_400(self, s3_cliente, *_):
        carpeta = self.carpeta('Muchos')
        Item.objects.bulk_create([
            Item(usuario=self.usuario, nombre=f'{i}.txt', tipo=Item.Tipo.ARCHIVO, padre=carpeta, file=f'files/{i}.txt', tamano_bytes=0)
            for i in range(1000)
        ])
        respuesta = self.copiar([carpeta.id], None)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('1000', respuesta.json()['errors'][0]['detail'])
        s3_cliente.return_value.copy_object.assert_not_called()


def jpeg_girado():
    """JPEG de 200x100 (izquierda roja, derecha azul) con EXIF 'girar 90°': de pie mide 100x200 con el rojo arriba."""
    from PIL import Image
    imagen = Image.new('RGB', (200, 100), (0, 0, 255))
    imagen.paste((255, 0, 0), (0, 0, 100, 100))
    exif = Image.Exif()
    exif[0x0112] = 6
    salida = io.BytesIO()
    imagen.save(salida, 'JPEG', exif=exif, quality=95)
    return salida.getvalue()


@mock.patch.object(registry, 'delete_related')
@mock.patch.object(registry, 'update_related')
@mock.patch.object(registry, 'update')
@mock.patch.object(registry, 'delete')
@mock.patch('items.services.ItemService.get_s3_client')
class MiniaturaTests(TestCase):
    """La tabla enseña una miniatura WebP de las imágenes en vez del icono."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(email='miniatura@prueba.com', password='Prueba1234!')
        self.cliente = APIClient()
        self.cliente.force_authenticate(self.usuario)

    def imagen(self, nombre='foto.jpg', mime='image/jpeg', **extra):
        return Item.objects.create(
            usuario=self.usuario, nombre=nombre, tipo=Item.Tipo.ARCHIVO,
            file=f'files/{nombre}', mime_type=mime, **{'tamano_bytes': 1000, **extra},
        )

    def guardada(self, s3):
        from PIL import Image
        llamada = s3.return_value.put_object.call_args.kwargs
        return llamada, Image.open(io.BytesIO(llamada['Body']))

    def test_hace_una_webp_cuadrada_y_de_pie(self, s3, *_):
        s3.return_value.get_object.return_value = {'Body': io.BytesIO(jpeg_girado())}
        item = self.imagen()
        ItemService.generar_miniatura(item)
        llamada, webp = self.guardada(s3)
        self.assertEqual(llamada['ContentType'], 'image/webp')
        self.assertTrue(llamada['Key'].startswith(f'users/{self.usuario.id}/m/'))
        self.assertEqual((webp.format, webp.size), ('WEBP', (112, 112)))
        rojo, azul = webp.convert('RGB').getpixel((56, 5)), webp.convert('RGB').getpixel((56, 106))
        self.assertGreater(rojo[0], 200)
        self.assertGreater(azul[2], 200)
        item.refresh_from_db()
        self.assertEqual(item.miniatura_key, llamada['Key'])

    def test_una_imagen_rota_se_queda_con_el_icono(self, s3, *_):
        s3.return_value.get_object.return_value = {'Body': io.BytesIO(b'esto no es un jpeg')}
        item = self.imagen()
        with self.assertLogs('items.services', level='WARNING'):
            ItemService.generar_miniatura(item)
        s3.return_value.put_object.assert_not_called()
        item.refresh_from_db()
        self.assertEqual(item.miniatura_key, '/fallida')

    def test_demasiado_grande_no_se_descarga(self, s3, *_):
        item = self.imagen(tamano_bytes=61 * 1024 * 1024)
        ItemService.generar_miniatura(item)
        s3.return_value.get_object.assert_not_called()
        self.assertEqual(item.miniatura_key, '/fallida')

    def test_el_svg_sale_de_su_png_y_nunca_del_svg(self, s3, *_):
        from PIL import Image
        png = io.BytesIO()
        Image.new('RGBA', (300, 200), (0, 128, 0, 255)).save(png, 'PNG')
        s3.return_value.get_object.return_value = {'Body': io.BytesIO(png.getvalue())}
        item = self.imagen('dibujo.svg', mime='image/svg+xml', preview_key='users/1/p/x.png')
        ItemService.generar_miniatura(item)
        self.assertEqual(s3.return_value.get_object.call_args.kwargs['Key'], 'users/1/p/x.png')
        self.assertNotEqual(item.miniatura_key, '/fallida')

    def test_otros_tipos_no_tienen_miniatura(self, s3, *_):
        for nombre, mime in [('a.pdf', 'application/pdf'), ('b.mp3', 'audio/mpeg'), ('c.svg', 'image/svg+xml')]:
            item = self.imagen(nombre, mime=mime)
            ItemService.generar_miniatura(item)
        s3.return_value.get_object.assert_not_called()
        s3.return_value.put_object.assert_not_called()

    def test_al_rehacerla_se_borra_la_anterior(self, s3, *_):
        s3.return_value.get_object.return_value = {'Body': io.BytesIO(jpeg_girado())}
        item = self.imagen(miniatura_key='users/1/m/vieja.webp')
        ItemService.generar_miniatura(item)
        s3.return_value.delete_object.assert_called_once_with(Bucket=mock.ANY, Key='users/1/m/vieja.webp')

    def test_el_endpoint_redirige_al_enlace_firmado(self, *_):
        item = self.imagen(miniatura_key='users/1/m/a.webp')
        respuesta = self.cliente.get(f'/api/items/{item.id}/miniatura/')
        self.assertEqual(respuesta.status_code, 302)
        destino = urlsplit(respuesta['Location'])
        self.assertTrue(destino.path.endswith('/users/1/m/a.webp'))
        self.assertEqual(parse_qs(destino.query)['response-content-type'], ['image/webp'])
        self.assertIn('private', respuesta['Cache-Control'])

    def test_sin_miniatura_o_ajena_da_404(self, *_):
        sin = self.imagen('sin.jpg')
        fallida = self.imagen('fallida.jpg', miniatura_key='/fallida')
        otro = Usuario.objects.create_user(email='otro-mini@prueba.com', password='Prueba1234!')
        ajena = Item.objects.create(
            usuario=otro, nombre='x.jpg', tipo=Item.Tipo.ARCHIVO, file='files/x.jpg',
            mime_type='image/jpeg', miniatura_key='users/9/m/x.webp',
        )
        for item in (sin, fallida, ajena):
            with self.subTest(item=item.nombre):
                self.assertEqual(self.cliente.get(f'/api/items/{item.id}/miniatura/').status_code, 404)

    def test_el_listado_dice_si_hay_miniatura(self, *_):
        self.imagen('con.jpg', miniatura_key='users/1/m/a.webp')
        self.imagen('sin.jpg')
        self.imagen('fallida.jpg', miniatura_key='/fallida')
        filas = self.cliente.get('/api/items/').json()['items']
        self.assertEqual({f['nombre']: f['tiene_miniatura'] for f in filas}, {'con.jpg': True, 'sin.jpg': False, 'fallida.jpg': False})

    def test_la_miniatura_se_borra_con_la_foto_y_no_es_huerfana(self, *_):
        self.imagen(miniatura_key='users/1/m/a.webp')
        self.imagen('rota.jpg', miniatura_key='/fallida')
        claves = ItemService.get_s3_keys_for_items(Item.objects.filter(usuario=self.usuario))
        self.assertIn('users/1/m/a.webp', claves)
        self.assertNotIn('/fallida', claves)
        self.assertIn('users/1/m/a.webp', ItemService.claves_registradas())
        self.assertNotIn('/fallida', ItemService.claves_registradas())
