from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

Usuario = get_user_model()

EMAIL = 'pruebas@pomba.test'
PASSWORD = 'Prueba1234!'


class SesionesTests(TestCase):
    """Login, logout, CSRF y cambio de contraseña con sesiones de Django."""

    def setUp(self):
        # El límite de logins vive en la caché y se acumularía entre pruebas
        cache.clear()
        self.usuario = Usuario.objects.create_user(email=EMAIL, password=PASSWORD)

    def cliente(self):
        # Sin enforce_csrf_checks el cliente de pruebas se salta el CSRF
        return APIClient(enforce_csrf_checks=True)

    def csrf(self, cliente):
        # Se relee siempre: login() rota el token
        if 'csrftoken' not in cliente.cookies:
            cliente.get('/api/auth/csrf/')
        return cliente.cookies['csrftoken'].value

    def login(self, cliente, password=PASSWORD):
        return cliente.post(
            '/api/auth/login/',
            {'email': EMAIL, 'password': password},
            format='json',
            HTTP_X_CSRFTOKEN=self.csrf(cliente),
        )

    def codigo_error(self, respuesta):
        return respuesta.json()['errors'][0]['code']

    def test_1_login_correcto(self):
        cliente = self.cliente()
        respuesta = self.login(cliente)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['email'], EMAIL)
        self.assertIn('sessionid', respuesta.cookies)
        self.assertTrue(respuesta.cookies['sessionid']['httponly'])
        self.assertEqual(cliente.get('/api/user/me/').status_code, 200)

    def test_2_login_password_mala(self):
        respuesta = self.login(self.cliente(), password='Incorrecta1234!')
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.codigo_error(respuesta), 'authentication_failed')
        self.assertNotIn('sessionid', respuesta.cookies)

    def test_3_login_sin_cabecera_csrf(self):
        cliente = self.cliente()
        self.csrf(cliente)  # Hay cookie; falta solo la cabecera
        respuesta = cliente.post(
            '/api/auth/login/', {'email': EMAIL, 'password': PASSWORD}, format='json'
        )
        self.assertEqual(respuesta.status_code, 403)
        self.assertNotIn('sessionid', respuesta.cookies)

    def test_4_me_sin_sesion(self):
        respuesta = self.cliente().get('/api/user/me/')
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.codigo_error(respuesta), 'not_authenticated')

    def test_5_patch_me_exige_csrf(self):
        cliente = self.cliente()
        self.login(cliente)
        sin_token = cliente.patch('/api/user/me/', {'nombre': 'Sin'}, format='json')
        self.assertEqual(sin_token.status_code, 403)
        self.assertEqual(self.codigo_error(sin_token), 'permission_denied')
        con_token = cliente.patch(
            '/api/user/me/', {'nombre': 'Con'}, format='json',
            HTTP_X_CSRFTOKEN=self.csrf(cliente),
        )
        self.assertEqual(con_token.status_code, 200)
        self.assertEqual(con_token.json()['nombre'], 'Con')

    def test_6_logout(self):
        cliente = self.cliente()
        self.login(cliente)
        sessionid = cliente.cookies['sessionid'].value
        respuesta = cliente.post('/api/auth/logout/', HTTP_X_CSRFTOKEN=self.csrf(cliente))
        self.assertEqual(respuesta.status_code, 204)
        # La cookie antigua ya no vale en el servidor
        cliente.cookies['sessionid'] = sessionid
        self.assertEqual(cliente.get('/api/user/me/').status_code, 403)

    def test_7_cambiar_password_cierra_las_demas_sesiones(self):
        cliente_a, cliente_b = self.cliente(), self.cliente()
        self.login(cliente_a)
        self.login(cliente_b)
        respuesta = cliente_a.post(
            '/api/user/me/cambiar-password/',
            {'password_actual': PASSWORD, 'password_nuevo': 'OtraClave5678!'},
            format='json',
            HTTP_X_CSRFTOKEN=self.csrf(cliente_a),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(cliente_a.get('/api/user/me/').status_code, 200)
        self.assertEqual(cliente_b.get('/api/user/me/').status_code, 403)

    def test_8_borrar_cuenta(self):
        cliente = self.cliente()
        self.login(cliente)
        sessionid = cliente.cookies['sessionid'].value
        respuesta = cliente.delete('/api/user/me/', HTTP_X_CSRFTOKEN=self.csrf(cliente))
        self.assertEqual(respuesta.status_code, 204)
        self.assertFalse(Usuario.objects.filter(email=EMAIL).exists())
        cliente.cookies['sessionid'] = sessionid
        self.assertEqual(cliente.get('/api/user/me/').status_code, 403)

    def test_9_limite_de_logins(self):
        cliente = self.cliente()
        for _ in range(5):
            self.assertEqual(self.login(cliente, password='Incorrecta1234!').status_code, 403)
        self.assertEqual(self.login(cliente).status_code, 429)

    def test_a_mismo_error_si_el_email_no_existe(self):
        password_mala = self.login(self.cliente(), password='Incorrecta1234!')
        cliente = self.cliente()
        email_inexistente = cliente.post(
            '/api/auth/login/',
            {'email': 'nadie@pomba.test', 'password': PASSWORD},
            format='json',
            HTTP_X_CSRFTOKEN=self.csrf(cliente),
        )
        # Respuesta idéntica: no revela qué emails tienen cuenta
        self.assertEqual(email_inexistente.status_code, password_mala.status_code)
        self.assertEqual(email_inexistente.json(), password_mala.json())

    def test_b_atributos_de_las_cookies(self):
        respuesta = self.login(self.cliente())
        sesion = respuesta.cookies['sessionid']
        csrf = respuesta.cookies['csrftoken']
        self.assertEqual(sesion['samesite'], 'Lax')
        self.assertEqual(int(sesion['max-age']), 7 * 24 * 60 * 60)
        self.assertEqual(csrf['samesite'], 'Lax')
        # El frontend tiene que poder leer csrftoken
        self.assertFalse(csrf['httponly'])

    def test_c_login_cambia_el_id_de_sesion(self):
        # Sesión "regalada" por un atacante antes del login (session fixation)
        plantada = SessionStore()
        plantada['algo'] = 'x'
        plantada.create()
        cliente = self.cliente()
        cliente.cookies[settings.SESSION_COOKIE_NAME] = plantada.session_key
        self.login(cliente)
        self.assertNotEqual(cliente.cookies['sessionid'].value, plantada.session_key)
        self.assertFalse(SessionStore().exists(plantada.session_key))

    def test_d_logout_sin_sesion(self):
        cliente = self.cliente()
        respuesta = cliente.post('/api/auth/logout/', HTTP_X_CSRFTOKEN=self.csrf(cliente))
        self.assertEqual(respuesta.status_code, 204)
