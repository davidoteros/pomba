// Estado en memoria de la demo: la cuenta de ejemplo y lo que el visitante va cambiando
import urlLogin from './ficheros/login.png?url'
import urlExplorador from './ficheros/explorador.png?url'
import urlBienvenida from './ficheros/bienvenida.pdf?url'
import urlMaquetaV1 from './ficheros/maqueta-v1.wav?url'
import urlMaquetaV2 from './ficheros/maqueta-v2.wav?url'
import urlNotas from './ficheros/notas.txt?url'
import urlAjito from './ficheros/ajito.jpg?url'

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

  crearArchivo({ nombre: 'Explorador.png', padre: fotos.id, url: urlExplorador, mime_type: 'image/png', tamano_bytes: 107415, favorito: true, fecha: haceDias(9), metadatos: { ancho: 1600, alto: 900 } })
  crearArchivo({ nombre: 'Login.png', padre: fotos.id, url: urlLogin, mime_type: 'image/png', tamano_bytes: 70461, fecha: haceDias(8), metadatos: { ancho: 1600, alto: 900 } })
  crearArchivo({ nombre: 'Bienvenida a Pomba.pdf', padre: documentos.id, url: urlBienvenida, mime_type: 'application/pdf', tamano_bytes: 14342, favorito: true, fecha: haceDias(3) })
  crearArchivo({ nombre: 'Notas.txt', padre: documentos.id, url: urlNotas, mime_type: 'text/plain', tamano_bytes: 81, fecha: haceDias(2) })
  crearArchivo({ nombre: 'Borrador viejo.txt', url: urlNotas, mime_type: 'text/plain', tamano_bytes: 81, eliminado: true, fecha: haceDias(30) })

  // La canción con dos versiones, para el control de versiones de audio
  const maqueta = crearArchivo({ nombre: 'Maqueta.wav', padre: musica.id, url: urlMaquetaV2, mime_type: 'audio/wav', tamano_bytes: 213424, fecha: haceDias(1), metadatos: { duracion_segundos: 4 } })
  estado.versiones.set(maqueta.id, [
    { id: 2, numero: 2, url: urlMaquetaV2, tamano_bytes: 213424, mime_type: 'audio/wav', metadatos: { duracion_segundos: 4 }, es_actual: true, fecha_creacion: haceDias(1) },
    { id: 1, numero: 1, url: urlMaquetaV1, tamano_bytes: 192476, mime_type: 'audio/wav', metadatos: { duracion_segundos: 4 }, es_actual: false, fecha_creacion: haceDias(6) },
  ])
}
