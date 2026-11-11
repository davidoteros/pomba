from .base import *

# En desarrollo no exigimos DJANGO_SECRET_KEY: si no está, usamos una fija para que
# el proyecto arranque recién clonado.
SECRET_KEY = SECRET_KEY or 'django-insecure-solo-para-desarrollo'

DEBUG = True

# En desarrollo publicamos el esquema OpenAPI para poder consultar las rutas en Swagger.
EXPONER_API_SCHEMA = True

ALLOWED_HOSTS = ['*']
