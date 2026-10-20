#!/bin/bash
set -e

cd /app

# Instalar dependencias solo si requirements.txt cambia
HASH_FILE="/app/.pip_hash"
if [ -f "requirements.txt" ]; then
    CURRENT_HASH=$(md5sum requirements.txt | cut -d' ' -f1)
    STORED_HASH=$(cat "$HASH_FILE" 2>/dev/null || echo "")

    if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
        echo "📦 Dependencias actualizadas, instalando..."
        pip install --no-cache-dir -r requirements.txt
        echo "$CURRENT_HASH" > "$HASH_FILE"
    else
        echo "✅ Dependencias sin cambios, saltando pip install."
    fi
fi

echo "🔄 Aplicando migraciones..."
python manage.py migrate --noinput

echo "🗄️ Creando tabla de caché..."
python manage.py createcachetable

echo "🚀 Iniciando servidor de desarrollo..."
exec python manage.py runserver 0.0.0.0:8000
