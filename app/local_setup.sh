#!/bin/bash
echo "🛠️ Preparando entorno local de Python..."

VENV_DIR="backend/libraries"
HASH_FILE="backend/.pip_hash_local"
REQUIREMENTS="backend/requirements.txt"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip

# md5sum en Linux, md5 en macOS
hash_file() {
    if command -v md5sum >/dev/null 2>&1; then
        md5sum "$1" | cut -d' ' -f1
    else
        md5 -q "$1"
    fi
}

if [ -f "$REQUIREMENTS" ]; then
    CURRENT_HASH=$(hash_file "$REQUIREMENTS")
    STORED_HASH=$(cat "$HASH_FILE" 2>/dev/null || echo "")

    if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
        echo "📦 Dependencias actualizadas, instalando en entorno local..."
        pip install --no-cache-dir -r "$REQUIREMENTS"
        echo "$CURRENT_HASH" > "$HASH_FILE"
    else
        echo "✅ Dependencias locales sin cambios, saltando pip install."
    fi
else
    echo "⚠️  No se encontró backend/requirements.txt."
fi

echo "🚀 Todo preparado!"
