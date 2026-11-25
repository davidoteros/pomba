// Estado en memoria de la demo: la cuenta de ejemplo y lo que el visitante va cambiando
import urlLogin from './ficheros/login.png?url'
import urlExplorador from './ficheros/explorador.png?url'
import urlBienvenida from './ficheros/bienvenida.pdf?url'
import urlNotas from './ficheros/notas.txt?url'
import urlAjito from './ficheros/ajito.jpg?url'
import urlMinimal from './ficheros/minimal-tech-house.mp3?url'
import urlMarga from './ficheros/marga.mp3?url'
import urlMaria from './ficheros/maria.mp3?url'
import urlMoruxo from './ficheros/moruxo.mp3?url'
import urlLembranzas from './ficheros/lembranzas.jpg?url'

// Miniaturas de la tabla (112 px WebP, como las que hace Django al subir)
const urlsMiniaturas = import.meta.glob('./ficheros/miniaturas/*.webp', { eager: true, query: '?url', import: 'default' })
const miniatura = (nombre) => urlsMiniaturas[`./ficheros/miniaturas/${nombre}.webp`]

// Mis fotos: nombre → URL; el tamaño y las medidas van en MIS_FOTOS
const urlsMisFotos = import.meta.glob('./ficheros/mis-fotos/*.jpg', { eager: true, query: '?url', import: 'default' })
const MIS_FOTOS = [
  ['049319', 167698, 1080, 1600], ['049321', 156806, 1600, 1080], ['049326', 278238, 1080, 1600],
  ['168237', 294847, 1600, 1080], ['411817', 473828, 1600, 1080], ['411821', 279423, 1600, 1080],
  ['411838', 316806, 1600, 1080], ['620137', 444191, 1078, 1600], ['620138', 425464, 1600, 1078],
  ['840403', 248539, 1078, 1600], ['840414', 196053, 1600, 1078],
]

export const CUOTA = 1024 ** 3
export const LIMITE_FICHERO = 100 * 1024 ** 2

export const estado = { items: new Map(), versiones: new Map(), subidas: new Map(), perfil: null, siguienteId: 1 }

function haceDias(dias) {
  return new Date(Date.now() - dias * 86_400_000).toISOString()
}

function crear(datos) {
  const id = estado.siguienteId++
  const fecha = datos.fecha ?? new Date().toISOString()
  const item = {
    id,
    nombre: datos.nombre,
    tipo: datos.tipo ?? 'archivo',
    padre: datos.padre ?? null,
    usuario: 1,
    url: datos.url ?? null,
    miniatura: datos.miniatura ?? null,
    tamano_bytes: datos.tamano_bytes ?? 0,
    mime_type: datos.mime_type ?? null,
    metadatos: datos.metadatos ?? {},
    favorito: datos.favorito ?? false,
    eliminado: datos.eliminado ?? false,
    fecha_eliminado: datos.eliminado ? fecha : null,
    fecha_creacion: fecha,
    fecha_modificacion: fecha,
  }
  estado.items.set(id, item)
  return item
}

export function crearCarpeta(nombre, padre, fecha) {
  return crear({ nombre, tipo: 'carpeta', padre, fecha })
}

export function crearArchivo(datos) {
  return crear({ ...datos, tipo: 'archivo' })
}

function temaGuardado() {
  try {
    return localStorage.getItem('theme') === 'oscuro' ? 'oscuro' : 'claro'
  } catch {
    return 'claro'
  }
}

// Vuelve a la cuenta de ejemplo del principio
export function reiniciar() {
  for (const subida of estado.subidas.values()) URL.revokeObjectURL(subida.url)
  estado.items.clear()
  estado.versiones.clear()
  estado.subidas.clear()
  estado.siguienteId = 1
  estado.perfil = {
    id: 1, email: 'invitado@pomba.demo', nombre: 'Invitado', apellidos: 'Demo',
    foto_perfil_url: urlAjito, tema: temaGuardado(),
  }

  const fotos = crearCarpeta('Fotos', null, haceDias(20))
  const musica = crearCarpeta('Música', null, haceDias(15))
  const documentos = crearCarpeta('Documentos', null, haceDias(10))
  const misFotos = crearCarpeta('Mis fotos', null, haceDias(18))

  MIS_FOTOS.forEach(([nombre, bytes, ancho, alto], i) => crearArchivo({
    nombre: `${nombre}.JPG`, padre: misFotos.id, url: urlsMisFotos[`./ficheros/mis-fotos/${nombre}.jpg`], miniatura: miniatura(nombre),
    mime_type: 'image/jpeg', tamano_bytes: bytes, fecha: haceDias(18 - i), metadatos: { ancho, alto },
  }))

  crearArchivo({ nombre: 'Explorador.png', padre: fotos.id, url: urlExplorador, miniatura: miniatura('explorador'), mime_type: 'image/png', tamano_bytes: 107415, favorito: true, fecha: haceDias(9), metadatos: { ancho: 1600, alto: 900 } })
  crearArchivo({ nombre: 'Login.png', padre: fotos.id, url: urlLogin, miniatura: miniatura('login'), mime_type: 'image/png', tamano_bytes: 70461, fecha: haceDias(8), metadatos: { ancho: 1600, alto: 900 } })
  crearArchivo({ nombre: 'Bienvenida a Pomba.pdf', padre: documentos.id, url: urlBienvenida, mime_type: 'application/pdf', tamano_bytes: 14342, favorito: true, fecha: haceDias(3) })
  crearArchivo({ nombre: 'Notas.txt', padre: documentos.id, url: urlNotas, mime_type: 'text/plain', tamano_bytes: 81, fecha: haceDias(2) })
  crearArchivo({ nombre: 'Borrador viejo.txt', url: urlNotas, mime_type: 'text/plain', tamano_bytes: 81, eliminado: true, fecha: haceDias(30) })

  crearArchivo({ nombre: 'Minimal Tech House.mp3', padre: musica.id, url: urlMinimal, mime_type: 'audio/mpeg', tamano_bytes: 4727117, fecha: haceDias(5), metadatos: { duracion_segundos: 295 } })
  const lembranzas = crearCarpeta('Lembranzas', musica.id, haceDias(14))
  crearArchivo({ nombre: 'Portada.jpg', padre: lembranzas.id, url: urlLembranzas, miniatura: miniatura('lembranzas'), mime_type: 'image/jpeg', tamano_bytes: 174062, fecha: haceDias(14), metadatos: { ancho: 1200, alto: 1200 } })
  crearArchivo({ nombre: 'Marga.mp3', padre: lembranzas.id, url: urlMarga, mime_type: 'audio/mpeg', tamano_bytes: 5571812, fecha: haceDias(14), metadatos: { duracion_segundos: 348 } })
  crearArchivo({ nombre: 'María.mp3', padre: lembranzas.id, url: urlMaria, mime_type: 'audio/mpeg', tamano_bytes: 5028883, fecha: haceDias(14), metadatos: { duracion_segundos: 314 } })
  crearArchivo({ nombre: 'Moruxo.mp3', padre: lembranzas.id, url: urlMoruxo, mime_type: 'audio/mpeg', tamano_bytes: 4938186, fecha: haceDias(14), metadatos: { duracion_segundos: 309 } })
}
