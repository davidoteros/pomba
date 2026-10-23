import io
import logging

import mutagen
from mutagen.flac import FLAC
from mutagen.id3 import ID3FileType
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from PIL import Image

logger = logging.getLogger(__name__)

#Pongo un límite de momento para indexar texto, pdfs los dejo para mas adelante
LIMITE_CONTENIDO_BYTES = 5 * 1024 * 1024  # 5 MB

MIMES_TEXTO = {
    'text/plain', 'text/markdown', 'text/x-markdown',
    'text/csv', 'application/csv', 'text/x-csv',
    'text/x-log',
}

MIMES_IMAGEN = {
    'image/jpeg', 'image/jpg', 'image/png',
    'image/webp', 'image/tiff', 'image/gif',
}

MIMES_AUDIO = {
    'audio/mpeg', 'audio/mp3', 'audio/flac',
    'audio/ogg', 'audio/mp4', 'audio/x-m4a',
    'audio/aac', 'audio/wav', 'audio/x-wav',
}


def extraer(datos: bytes, mime_type: str, tamano_bytes: int) -> dict:
    """
    Extrae contenido textual y metadatos de un archivo según su mime_type.

    Devuelve {'contenido': str, 'metadatos': dict}.
    Nunca lanza excepción: los errores se loggean y devuelven vacío.
    """
    resultado = {'contenido': '', 'metadatos': {}}
    mime = (mime_type or '').lower().split(';')[0].strip()

    try:
        if mime in MIMES_TEXTO:
            if tamano_bytes <= LIMITE_CONTENIDO_BYTES:
                resultado['contenido'] = _texto_plano(datos)
        elif mime in MIMES_IMAGEN:
            resultado['metadatos'] = _imagen(datos)
        elif mime in MIMES_AUDIO:
            resultado['metadatos'] = _audio(datos)
    except Exception as e:
        logger.warning("No se pudieron extraer datos (mime=%s): %s", mime_type, e)


    return resultado



def _texto_plano(datos):
    return datos.decode('utf-8', errors='replace')


def _imagen(datos):
    # IDs de tags EXIF que nos interesan
    TAGS_EXIF = {
        271  : 'camara_marca',
        272  : 'camara_modelo',
        36867: 'fecha_captura',
        40962: 'ancho',
        40963: 'alto',
    }

    metadatos = {}

    imagen = Image.open(io.BytesIO(datos))
    metadatos['ancho'] = imagen.width
    metadatos['alto'] = imagen.height

    exif = imagen.getexif()
    if exif:
        for tag_id, clave in TAGS_EXIF.items():
            valor = exif.get(tag_id)
            if valor:
                metadatos[clave] = str(valor).strip()

    return metadatos


def _audio(datos):
    metadatos = {}

    audio = mutagen.File(io.BytesIO(datos))
    if audio is None:
        return metadatos

    if hasattr(audio, 'info') and hasattr(audio.info, 'length'):
        metadatos['duracion_segundos'] = int(audio.info.length)

    if isinstance(audio, (FLAC, OggVorbis)):
        _tags_vorbis(audio, metadatos)
    elif isinstance(audio, MP4):
        _tags_mp4(audio, metadatos)
    elif isinstance(audio, ID3FileType):
        _tags_id3(audio, metadatos)

    return metadatos


def _tags_vorbis(audio, metadatos):
    mapeo = {
        'artist': 'artista',
        'album' : 'album',
        'title' : 'titulo',
        'date'  : 'año',
        'genre' : 'genero',
    }
    for tag, campo in mapeo.items():
        valores = audio.get(tag, [])
        if valores:
            metadatos[campo] = _año_a_texto(campo, valores[0])


def _tags_mp4(audio, metadatos):
    mapeo = {
        '©ART': 'artista',
        '©alb': 'album',
        '©nam': 'titulo',
        '©day': 'año',
        '©gen': 'genero',
    }
    for tag, campo in mapeo.items():
        valores = audio.get(tag, [])
        if valores:
            metadatos[campo] = _año_a_texto(campo, str(valores[0]))


def _tags_id3(audio, metadatos):
    if not audio.tags:
        return
    mapeo = {
        'TPE1': 'artista',
        'TALB': 'album',
        'TIT2': 'titulo',
        'TDRC': 'año',
        'TCON': 'genero',
    }
    for tag, campo in mapeo.items():
        frame = audio.tags.get(tag)
        if frame and frame.text:
            metadatos[campo] = _año_a_texto(campo, str(frame.text[0]))


def _año_a_texto(campo, valor):
    """Convierte el campo año a texto. El resto lo devuelve como str."""
    valor = str(valor).strip()
    if campo == 'año':
        try:
            return int(valor[:4])
        except (ValueError, IndexError):
            return None
    return valor
