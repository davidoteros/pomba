import threading
import time
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from django_elasticsearch_dsl.registries import registry
from rest_framework.test import APIClient

from items.models import Item, SubidaPendiente
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
