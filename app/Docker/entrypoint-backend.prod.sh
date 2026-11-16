#!/bin/bash
set -e

cd /app


if [ "$DJANGO_SETTINGS_MODULE" != "core.settings.production" ]; then
    echo "ERROR: DJANGO_SETTINGS_MODULE vale '$DJANGO_SETTINGS_MODULE' y en producción debe ser core.settings.production. Quítalo del .env." >&2
    exit 1
fi

echo "Aplicando migraciones..."
python manage.py migrate --noinput

echo "Creando tabla de caché..."
python manage.py createcachetable

echo "Borrando sesiones caducadas..."
python manage.py clearsessions

echo "Recopilando ficheros estáticos..."
python manage.py collectstatic --noinput

echo "Iniciando Gunicorn..."
exec gunicorn core.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 300 \
    --access-logfile - \
    --error-logfile -
