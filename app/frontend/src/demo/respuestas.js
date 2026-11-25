// Backend falso de la demo: tonto a propósito (sin cuota ni reglas de nombre), solo imita las respuestas de Django
import { http, HttpResponse } from 'msw/http'
import { estado, crearArchivo, crearCarpeta, CUOTA, LIMITE_FICHERO } from './datos.js'

const API = '/api'

// Mismo formato que drf-standardized-errors; 501 para que Vue enseñe el motivo en las notificaciones
function noDisponible() {
  return HttpResponse.json(
    { type: 'server_error', errors: [{ code: 'demo', detail: 'No disponible en la demo.', attr: null }] },
    { status: 501 },
  )
}

function noEncontrado() {
  return HttpResponse.json({ detail: 'Elemento no encontrado.' }, { status: 404 })
}

function tipoVisor(mime) {
  if (!mime || mime === 'image/svg+xml') return null
  if (mime === 'application/pdf') return 'pdf'
  const familia = mime.split('/')[0]
  return { image: 'imagen', audio: 'audio', video: 'video' }[familia] ?? null
}

function activo(id) {
  const item = estado.items.get(Number(id))
  return item && !item.eliminado ? item : null
}

function hijos(id) {
  return [...estado.items.values()].filter((i) => i.padre === id)
}

function serializar(item) {
  const { url, ...resto } = item
  const visor = item.tipo === 'archivo' ? tipoVisor(item.mime_type) : null
  return {
    ...resto,
    file: url,
    previsualizable: visor !== null,
    tipo_visor: visor,
    tiene_hijos: hijos(item.id).some((h) => h.eliminado === item.eliminado),
    // Como Django con VERSIONES_AUDIO=false: sin pestaña Versiones
    admite_versiones: false,
  }
}

// Como os.path.splitext: "notas.txt" → ["notas", ".txt"], ".bashrc" → [".bashrc", ""]
function separarExtension(nombre) {
  const inicio = nombre.search(/[^.]/)
  const punto = nombre.lastIndexOf('.')
  return inicio !== -1 && punto > inicio ? [nombre.slice(0, punto), nombre.slice(punto)] : [nombre, '']
}

// Como _nombre_disponible de Django: si ya existe en la carpeta, "notas (1).txt"
function nombreDisponible(nombre, padre) {
  const existe = (n) => [...estado.items.values()].some((i) => !i.eliminado && i.padre === padre && i.nombre === n)
  if (!existe(nombre)) return nombre
  const [base, extension] = separarExtension(nombre)
  let contador = 1
  while (existe(`${base} (${contador})${extension}`)) contador++
  return `${base} (${contador})${extension}`
}

// Carpetas antes que archivos y luego por nombre, como el order_by del backend
function ordenar(lista) {
  return lista.sort((a, b) => (a.tipo === b.tipo ? a.nombre.localeCompare(b.nombre, 'es') : a.tipo === 'carpeta' ? -1 : 1))
}

function descendientes(ids) {
  const todos = new Set(ids.map(Number))
  let crecido = true
  while (crecido) {
    crecido = false
    for (const i of estado.items.values()) {
      if (i.padre !== null && todos.has(i.padre) && !todos.has(i.id)) {
        todos.add(i.id)
        crecido = true
      }
    }
  }
  return [...todos].map((id) => estado.items.get(id)).filter(Boolean)
}

function migas(carpetaId) {
  const ruta = []
  let actual = estado.items.get(Number(carpetaId))
  while (actual) {
    ruta.unshift({ id: actual.id, label: actual.nombre })
    actual = estado.items.get(actual.padre)
  }
  return [{ id: null, label: 'Inicio' }, ...ruta]
}

function ocupado() {
  let total = 0
  for (const item of estado.items.values()) total += item.tamano_bytes
  for (const [itemId, lista] of estado.versiones) {
    for (const v of lista) if (!v.es_actual && estado.items.has(itemId)) total += v.tamano_bytes
  }
  return total
}

function urlEnUso(url) {
  if ([...estado.items.values()].some((i) => i.url === url)) return true
  return [...estado.versiones.values()].some((lista) => lista.some((v) => v.url === url))
}

// Una copia comparte la dirección blob: con su original: solo se suelta cuando nadie la usa
function borrar(item) {
  estado.items.delete(item.id)
  estado.versiones.delete(item.id)
  if (item.url?.startsWith('blob:') && !urlEnUso(item.url)) URL.revokeObjectURL(item.url)
}

function sinAcentos(texto) {
  return texto.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()
}

let siguienteSubida = 1

function entregarPase() {
  const key = `demo/${siguienteSubida++}`
  return HttpResponse.json({ url_subida: `${location.origin}/__demo_subida__/${key}`, key })
}

function listarVersiones(item) {
  const lista = estado.versiones.get(item.id) ?? []
  const actual = lista.find((v) => v.es_actual)
  return {
    versiones: lista.map(({ url, ...v }) => v),
    numero_actual: actual ? actual.numero : lista.length + 1,
  }
}

function aplicarVersion(item, version) {
  for (const v of estado.versiones.get(item.id)) v.es_actual = v === version
  Object.assign(item, {
    url: version.url, tamano_bytes: version.tamano_bytes, mime_type: version.mime_type,
    metadatos: version.metadatos, fecha_modificacion: new Date().toISOString(),
  })
}

export const respuestas = [
  // --- Sesión y perfil ---
  http.get(`${API}/auth/csrf/`, () => new HttpResponse(null, { status: 204 })),
  http.post(`${API}/auth/login/`, () => HttpResponse.json(estado.perfil)),
  http.post(`${API}/auth/logout/`, () => new HttpResponse(null, { status: 204 })),
  http.post(`${API}/user/register/`, () => HttpResponse.json(estado.perfil, { status: 201 })),
  http.get(`${API}/user/me/`, () => HttpResponse.json(estado.perfil)),
  http.patch(`${API}/user/me/`, async ({ request }) => {
    const { nombre, apellidos, tema } = await request.json()
    Object.assign(estado.perfil, Object.fromEntries(Object.entries({ nombre, apellidos, tema }).filter(([, v]) => v !== undefined)))
    return HttpResponse.json(estado.perfil)
  }),
  http.post(`${API}/user/me/foto/`, async ({ request }) => {
    const foto = (await request.formData()).get('foto_perfil')
    if (estado.perfil.foto_perfil_url) URL.revokeObjectURL(estado.perfil.foto_perfil_url)
    estado.perfil.foto_perfil_url = URL.createObjectURL(foto)
    return HttpResponse.json(estado.perfil)
  }),
  http.post(`${API}/user/me/cambiar-email/`, noDisponible),
  http.post(`${API}/user/me/cambiar-password/`, noDisponible),
  http.delete(`${API}/user/me/`, noDisponible),

  // --- Listado, búsqueda y espacio ---
  http.get(`${API}/items/`, ({ request }) => {
    const p = new URL(request.url).searchParams
    const carpeta = p.get('carpeta') ? Number(p.get('carpeta')) : null
    const papelera = p.get('papelera') === 'true'
    let lista = [...estado.items.values()].filter((i) => i.eliminado === papelera)

    if (p.get('recientes') === 'true') {
      lista = lista.filter((i) => i.tipo === 'archivo')
        .sort((a, b) => b.fecha_modificacion.localeCompare(a.fecha_modificacion)).slice(0, 30)
    } else {
      if (carpeta) lista = lista.filter((i) => i.padre === carpeta)
      else if (p.get('favorito') === 'true') lista = lista.filter((i) => i.favorito)
      else if (papelera) lista = lista.filter((i) => !estado.items.get(i.padre)?.eliminado)
      else lista = lista.filter((i) => i.padre === null)
      ordenar(lista)
    }
    return HttpResponse.json({ items: lista.map(serializar), breadcrumb: migas(carpeta) })
  }),
  http.get(`${API}/items/buscar/`, ({ request }) => {
    const q = (new URL(request.url).searchParams.get('q') ?? '').trim()
    const buscado = sinAcentos(q)
    const lista = [...estado.items.values()].filter((i) => !i.eliminado && sinAcentos(i.nombre).includes(buscado))
    return HttpResponse.json({ items: ordenar(lista).map(serializar), query: q })
  }),
  http.get(`${API}/items/espacio/`, () => {
    const usado = ocupado()
    return HttpResponse.json({ ocupado: usado, libre: Math.max(CUOTA - usado, 0), cuota: CUOTA, limite_fichero: LIMITE_FICHERO })
  }),

  // --- Crear, renombrar, mover, favoritos y papelera ---
  http.post(`${API}/items/`, async ({ request }) => {
    const { nombre, padre } = await request.json()
    return HttpResponse.json(serializar(crearCarpeta(nombre.trim(), padre ?? null)), { status: 201 })
  }),
  http.post(`${API}/items/crear_arbol_carpetas/`, async ({ request }) => {
    const { rutas, padre } = await request.json()
    const mapa = {}
    for (const ruta of rutas) {
      const partes = ruta.split('/')
      const padreId = partes.length === 1 ? (padre ?? null) : mapa[partes.slice(0, -1).join('/')]
      mapa[ruta] = crearCarpeta(partes.at(-1).trim(), padreId).id
    }
    return HttpResponse.json({ mapa })
  }),
  http.post(`${API}/items/:id/renombrar/`, async ({ params, request }) => {
    const item = activo(params.id)
    if (!item) return noEncontrado()
    item.nombre = (await request.json()).nombre.trim()
    item.fecha_modificacion = new Date().toISOString()
    return HttpResponse.json({ mensaje: 'Renombrado correctamente', nombre: item.nombre })
  }),
  http.post(`${API}/items/mover/`, async ({ request }) => {
    const { ids, destino } = await request.json()
    const padre = destino ?? null
    for (const id of ids) {
      const item = activo(id)
      if (item && item.padre !== padre) {
        item.nombre = nombreDisponible(item.nombre, padre)
        item.padre = padre
      }
    }
    return HttpResponse.json({ detail: `Se han movido ${ids.length} elementos.` })
  }),
  http.post(`${API}/items/copiar/`, async ({ request }) => {
    const { ids, destino } = await request.json()
    // Primero el árbol entero (carpetas antes que sus hijos, sin la papelera) y luego las copias, como Django
    const orden = ids.map(activo).filter(Boolean).sort((a, b) => a.id - b.id)
    const raices = new Set(orden.map((i) => i.id))
    const vistos = new Set(raices)
    for (let n = 0; n < orden.length; n++) {
      if (orden[n].tipo !== 'carpeta') continue
      const nuevos = hijos(orden[n].id).filter((h) => !h.eliminado && !vistos.has(h.id))
      nuevos.forEach((h) => vistos.add(h.id))
      orden.push(...nuevos)
    }
    const copias = new Map()
    for (const original of orden) {
      const esRaiz = raices.has(original.id)
      const padre = esRaiz ? (destino ?? null) : copias.get(original.padre).id
      const nombre = esRaiz ? nombreDisponible(original.nombre, padre) : original.nombre
      const copia = original.tipo === 'carpeta'
        ? crearCarpeta(nombre, padre)
        : crearArchivo({
          nombre, padre, url: original.url, mime_type: original.mime_type,
          tamano_bytes: original.tamano_bytes, metadatos: structuredClone(original.metadatos),
        })
      copias.set(original.id, copia)
    }
    return HttpResponse.json({ detail: `Se han copiado ${copias.size} elementos.`, copiados: copias.size })
  }),
  http.post(`${API}/items/favorito/`, async ({ request }) => {
    const item = estado.items.get(Number((await request.json()).id))
    if (!item) return noEncontrado()
    item.favorito = !item.favorito
    return HttpResponse.json({ detail: 'Favorito actualizado correctamente.', favorito: item.favorito })
  }),
  http.post(`${API}/items/trash/`, async ({ request }) => {
    const lista = descendientes((await request.json()).ids)
    const ahora = new Date().toISOString()
    for (const i of lista) Object.assign(i, { eliminado: true, fecha_eliminado: ahora })
    return HttpResponse.json({ detail: `Se han movido ${lista.length} elementos a la papelera.` })
  }),
  http.post(`${API}/items/restaurar/`, async ({ request }) => {
    const lista = descendientes((await request.json()).ids)
    for (const i of lista) Object.assign(i, { eliminado: false, fecha_eliminado: null })
    return HttpResponse.json({ detail: `Se han restaurado ${lista.length} elementos.` })
  }),
  http.post(`${API}/items/restaurar_papelera/`, () => {
    const lista = [...estado.items.values()].filter((i) => i.eliminado)
    for (const i of lista) Object.assign(i, { eliminado: false, fecha_eliminado: null })
    return HttpResponse.json({ detail: `Se han restaurado ${lista.length} elementos.` })
  }),
  http.delete(`${API}/items/eliminar_definitivo/`, async ({ request }) => {
    const lista = descendientes((await request.json()).ids).filter((i) => i.eliminado)
    lista.forEach(borrar)
    return HttpResponse.json({ detail: `Se han eliminado ${lista.length} elementos permanentemente.`, deleted_count: lista.length, s3_keys_deleted: 0 })
  }),
  http.post(`${API}/items/vaciar_papelera/`, () => {
    const lista = [...estado.items.values()].filter((i) => i.eliminado)
    lista.forEach(borrar)
    return HttpResponse.json({ detail: 'Papelera vaciada correctamente.', deleted_count: lista.length, s3_keys_deleted: 0 })
  }),

  // --- Subida: el "Garage" de la demo es un mapa en memoria ---
  http.post(`${API}/items/solicitar_subida/`, entregarPase),
  http.put('*/__demo_subida__/demo/:n', async ({ params, request }) => {
    const blob = await request.blob()
    estado.subidas.set(`demo/${params.n}`, { url: URL.createObjectURL(blob), tamano: blob.size })
    return new HttpResponse(null, { status: 200 })
  }),
  http.post(`${API}/items/confirmar_subida/`, async ({ request }) => {
    const { nombre, key, padre, mime_type } = await request.json()
    const subida = estado.subidas.get(key)
    if (!subida) return HttpResponse.json({ detail: 'Key no válida.' }, { status: 400 })
    estado.subidas.delete(key)
    const item = crearArchivo({
      nombre: nombreDisponible(nombre, padre ?? null), padre: padre ?? null,
      url: subida.url, mime_type, tamano_bytes: subida.tamano,
    })
    return HttpResponse.json(serializar(item), { status: 201 })
  }),

  // --- Ver y descargar (descargar sacaría al visitante de la demo) ---
  http.get(`${API}/items/:id/previsualizar/`, ({ params }) => {
    const item = activo(params.id)
    if (!item) return noEncontrado()
    return HttpResponse.json({ url: item.url })
  }),
  http.get(`${API}/items/:id/descargar_archivo/`, noDisponible),
  http.post(`${API}/items/descargar/`, noDisponible),

  // --- Versiones de audio ---
  http.get(`${API}/items/:id/versiones/`, ({ params }) => {
    const item = activo(params.id)
    if (!item) return noEncontrado()
    return HttpResponse.json(listarVersiones(item))
  }),
  http.post(`${API}/items/:id/versiones/solicitar_subida/`, ({ params }) => {
    const item = activo(params.id)
    if (!item) return noEncontrado()
    return entregarPase()
  }),
  http.post(`${API}/items/:id/versiones/confirmar_subida/`, async ({ params, request }) => {
    const item = activo(params.id)
    if (!item) return noEncontrado()
    const { key, mime_type } = await request.json()
    const subida = estado.subidas.get(key)
    if (!subida) return HttpResponse.json({ detail: 'Key no válida.' }, { status: 400 })
    estado.subidas.delete(key)
    const lista = estado.versiones.get(item.id) ?? []
    const numero = Math.max(0, ...lista.map((v) => v.numero)) + 1
    const version = {
      id: Date.now(), numero, url: subida.url, tamano_bytes: subida.tamano,
      mime_type: mime_type || item.mime_type, metadatos: {}, es_actual: true, fecha_creacion: new Date().toISOString(),
    }
    estado.versiones.set(item.id, [version, ...lista])
    aplicarVersion(item, version)
    return HttpResponse.json(serializar(item))
  }),
  http.post(`${API}/items/:id/versiones/:num/activar/`, ({ params }) => {
    const item = activo(params.id)
    const version = item && estado.versiones.get(item.id)?.find((v) => v.numero === Number(params.num))
    if (!version) return HttpResponse.json({ detail: 'Versión no encontrada.' }, { status: 404 })
    aplicarVersion(item, version)
    return HttpResponse.json(serializar(item))
  }),
  http.get(`${API}/items/:id/versiones/:num/previsualizar/`, ({ params }) => {
    const item = activo(params.id)
    const version = item && estado.versiones.get(item.id)?.find((v) => v.numero === Number(params.num))
    if (!version) return HttpResponse.json({ detail: 'Versión no encontrada.' }, { status: 404 })
    return HttpResponse.json({ url: version.url })
  }),
  http.get(`${API}/items/:id/versiones/:num/descargar/`, noDisponible),
  http.delete(`${API}/items/:id/versiones/:num/`, ({ params }) => {
    const item = activo(params.id)
    const lista = item && estado.versiones.get(item.id)
    const version = lista?.find((v) => v.numero === Number(params.num))
    if (!version) return HttpResponse.json({ detail: 'Versión no encontrada.' }, { status: 404 })
    if (version.es_actual) {
      return HttpResponse.json({ detail: 'No puedes eliminar la versión activa. Marca otra como actual primero.' }, { status: 400 })
    }
    estado.versiones.set(item.id, lista.filter((v) => v !== version))
    return new HttpResponse(null, { status: 204 })
  }),

  // Cualquier otra ruta de la API
  http.all(`${API}/*`, noDisponible),
]
