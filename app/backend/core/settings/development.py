from .base import *

# En desarrollo no exigimos DJANGO_SECRET_KEY: si no está, usamos una fija para que
# el proyecto arranque recién clonado.
SECRET_KEY = SECRET_KEY or 'django-insecure-solo-para-desarrollo'

DEBUG = True

# En desarrollo publicamos el esquema OpenAPI para poder consultar las rutas en Swagger.
EXPONER_API_SCHEMA = True

ALLOWED_HOSTS = ['*']

# Afecta a todas las peticiones (GET, POST, etc...)
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
]

# Solo afecta a peticiones que modifican estado (PUT, DELETE, PATCH, POST)
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:5173',
]
