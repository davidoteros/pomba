from datetime import timedelta
from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =========================================================
# APLICACIONES
# =========================================================

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

LOCAL_APPS = [
    'users',
    'items',
    'storage',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'storages',
    'django_elasticsearch_dsl',
    'drf_standardized_errors',
    'drf_spectacular',
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS + THIRD_PARTY_APPS

# =========================================================
# MIDDLEWARE
# =========================================================

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# =========================================================
# URLS / TEMPLATES / WSGI
# =========================================================

# Aquí le decimos a Django donde va a buscar las rutas
ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Le dice a Gunicorn donde comunicarse con Django
WSGI_APPLICATION = 'core.wsgi.application'

# =========================================================
# BASE DE DATOS (POSTGRESQL)
# =========================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST', 'db'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# =========================================================
# ELASTICSEARCH
# =========================================================

ELASTICSEARCH_DSL = {
    'default': {
        'hosts': os.environ.get('ELASTICSEARCH_URL', 'http://elasticsearch:9200')
    },
}

# =========================================================
# GARAGE (S3 COMPATIBLE STORAGE)
# =========================================================

# Usuario y contraseña para autenticarse
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')


# Carpeta donde se guardan los ficheros
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME', 'pomba-app')
# Url interna de Garage dentro de docker
AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL', 'http://garage:3900')
#Garage no utiliza regiones, pero la librería lo exige
AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'garage')

# Construir la URL del fichero S3
AWS_S3_ADDRESSING_STYLE = 'path'
# Algoritmo criptográfico para autenticar las peticiones
AWS_S3_SIGNATURE_VERSION = 's3v4'
# No aplicamos permisos por fichero individual
AWS_DEFAULT_ACL = None
# Evitamos sobreescritura si hay dos ficheros con el mismo nombre
# Django genera nombre único para el segundo
AWS_S3_FILE_OVERWRITE = False

# URL pública de Garage accesible desde el navegador.
# Django usa AWS_S3_ENDPOINT_URL (http://garage:3900) para operar con S3 internamente, pero las URLs presignadas deben generarse con el endpoint público para que el navegador pueda resolverlas.
GARAGE_PUBLIC_URL = os.environ.get('GARAGE_PUBLIC_URL', 'http://localhost:3900')

STORAGES = {
    # Ficheros de usuario para Garage S3
    'default': {
        'BACKEND': 'storage.backends.GarageStorage',
        'OPTIONS': {
            'addressing_style': 'path',
        },
    },
    # Estáticos desde disco local del servidor
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

STATIC_URL = '/static_backend/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# =========================================================
# AUTH
# =========================================================

AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# =========================================================
# REST FRAMEWORK / JWT
# =========================================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'EXCEPTION_HANDLER': 'drf_standardized_errors.handler.exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # Nº de proxies  delante de Django (hoy solo Nginx). Sin esto DRF usa la cabecera y pueden cambiar la IP para probar por fuerza bruta.
    # X-Forwarded-For entera como IP y el cliente puede inventarse una distinta en cada intento para saltarse los límites. Si se añade otro proxy delante (p. ej. Cloudflare), subirlo.
    'NUM_PROXIES': 1,
    'DEFAULT_THROTTLE_RATES': {
        'login': '5/min',
        'registro': '3/hour',
        'cambiar_password': '5/hour',
    },
}

# Caché en Postgres para que los workers de Gunicorn compartan los contadores de los límites
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache',
    }
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Pomba API',
    'DESCRIPTION': 'API REST para la plataforma de almacenamiento Pomba.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

# Publicar el esquema OpenAPI (/api/schema/ y Swagger/Redoc). Desactivado por defecto
EXPONER_API_SCHEMA = os.environ.get('EXPONER_API_SCHEMA', 'false').lower() == 'true'

DRF_STANDARDIZED_ERRORS = {'ENABLE_IN_DEBUG_FOR_UNHANDLED_EXCEPTIONS': True}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=2),
    'ROTATE_REFRESH_TOKENS': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# =========================================================
# SUBIDA DE ARCHIVOS
# =========================================================

# Archivos por encima de este tamaño se escriben en disco temporal en lugar de RAM.
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024 # 10 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 500 * 1024 * 1024 # 500 MB - red de seguridad para subidas multipart (aunque esta desactivado por si acaso lo dejo)

# Limites de las subidas presignadas
# Se comprueban al pedir la URL presignada y otra vez al confirmar, con el tamaño real.

_SUFIJOS_TAMANO = {'k': 1024, 'm': 1024 ** 2, 'g': 1024 ** 3}


def tamano_a_bytes(valor, variable):
    """
    Convierte un tamaño con sufijo de nginx ('2g', '25m', '512k') a bytes.

    Existe para que el limite por fichero se escriba una sola vez, en la variable
    POMBA_LIMITE_FICHERO: nginx la usa tal cual en client_max_body_size 
    y aqui se traduce a bytes. Asi las dos capas que vigilan
    el mismo limite no pueden desincronizarse.

    Si el valor no es valido, falla al arrancar.
    """
    original = valor
    valor = str(valor).strip().lower()
    multiplicador = _SUFIJOS_TAMANO.get(valor[-1:], 1)
    if multiplicador > 1:
        valor = valor[:-1]

    if not (valor.isascii() and valor.isdigit()):
        raise ImproperlyConfigured(
            f'{variable}={original!r} no es un tamaño válido. '
            'Escribe un número entero seguido de k, m o g (por ejemplo 2g, 500m, '
            '512k), o el número de bytes sin letra (1048576). '
            'Es la misma variable que usa nginx en client_max_body_size, '
            'así que debe llevar un formato que los dos entiendan.'
        )

    bytes_totales = int(valor) * multiplicador

    # Un limite de 0 dejaria el servicio inservible en silencio: ninguna subida,
    # ni de 1 byte, pasaria la comprobacion de cuota.
    if bytes_totales == 0:
        raise ImproperlyConfigured(
            f'{variable}={original!r} deja el límite en 0 bytes, '
            'con lo que no se podría subir ningún archivo.'
        )

    return bytes_totales


# La misma variable que nginx pone en el client_max_body_size del :3900.
LIMITE_FICHERO_BYTES = tamano_a_bytes(
    os.environ.get('POMBA_LIMITE_FICHERO') or '2g', 'POMBA_LIMITE_FICHERO',
)

# Cuota total por usuario. Solo la usa Django: nginx no sabe de usuarios ni de cuotas.
CUOTA_USUARIO_BYTES = int(os.environ.get('CUOTA_USUARIO_BYTES', 20 * 1024 ** 3))    # 20 GB

# Margen de vida de una subida pendiente.
SUBIDA_PENDIENTE_MINUTOS = int(os.environ.get('SUBIDA_PENDIENTE_MINUTOS', 60))

# =========================================================
# LOCALIZACIÓN
# =========================================================

LANGUAGE_CODE = 'es-ES'
TIME_ZONE = 'Europe/Madrid'
USE_I18N = True
USE_TZ = True
