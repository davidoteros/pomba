#!/bin/bash
set -e

cd /app

echo "Aplicando migraciones..."
python manage.py migrate --noinput

echo "Creando tabla de caché..."
python manage.py createcachetable

echo "Recopilando ficheros estáticos..."
python manage.py collectstatic --noinput

echo "Iniciando Gunicorn..."
exec gunicorn core.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 300 \
    --access-logfile - \
    --error-logfile -
