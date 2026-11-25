import { defineStore } from 'pinia'
import { apiItems } from '@/api/items'
import { getErrorMessage, mensajeDeAccion, motivoParaUsuario } from '@/utils/errors'
import { formatBytes } from '@/utils/bytes'
import { fromEvent } from 'file-selector'

const NOTIF_DURACION_EXITO = 3
const NOTIF_DURACION_ERROR = 5

// Ruta dentro de lo elegido o soltado, sin "/" ni "./" delante: "musica/rock/cancion.mp3"
function rutaRelativa(file) {
  return (file.relativePath || file.webkitRelativePath || file.name).replace(/^\.?\//, '')
}

export const useGestorItems = defineStore('items', {
  // Datos reactivos del store. Equivale a data() en un componente Vue.
  state: () => ({
    items: [],
    breadcrumb: [],
    loading: false,
    currentParams: {},
    loadToken: 0,
    queryBusqueda: '',

    seleccion: {
      ids: [],
      lastIndex: null,
    },

    // Cortar o copiar y pegar: qué se lleva, de qué carpetas sale y si se mueve ('cortar') o se duplica ('copiar')
    portapapeles: {
      ids: [],
      padres: [],
      modo: null,
    },

    // Mover arrastrando
    arrastre: {
      ids: [],
      destino: null,
      motivo: null,
    },

    modal: {
      open: false,
      name: null,
      payload: null,
    },

    notificaciones: [],

    // { ocupado, libre, cuota, limite_fichero } en bytes; null hasta que responde el servidor
    espacio: null,

    panelInfo: {
      visible: false,
      itemId: null,
    },
  }),

  // Propiedades calculadas derivadas del state. Se cachean y solo se recalculan cuando cambian los datos de los que dependen.
  getters: {
    itemPanelInfo: (state) => state.items.find((i) => i.id === state.panelInfo.itemId) ?? null,

    itemsSeleccionados(state) {
      const set = new Set(state.seleccion.ids)
      return state.items.filter((i) => set.has(i.id))
    },
    descargando: (state) =>
      state.notificaciones.some((n) => n.id === 'descargar' && n.tipo === 'cargando'),

    // La ruta da el id como texto; null es la raíz
    carpetaAbiertaId: (state) => (state.currentParams.carpeta ? Number(state.currentParams.carpeta) : null),

    esDestinoArrastre: (state) => (id) => state.arrastre.destino?.id === id,

    estaCortado: (state) => (id) => state.portapapeles.modo === 'cortar' && state.portapapeles.ids.includes(id),
  },

  // Funciones que modifican el state o llaman a la API. Equivalen a methods en un componente Vue.
  actions: {

    // === PANEL DE INFORMACIÓN ================================

    abrirPanelInfo(item) {
      this.panelInfo.visible = true
      this.panelInfo.itemId = item.id
    },

    cerrarPanelInfo() {
      this.panelInfo.visible = false
      this.panelInfo.itemId = null
    },

    // === MODALES ============================================

    abrirModal(name, payload = null) {
      this.modal.open = true
      this.modal.name = name
      this.modal.payload = payload
    },

    cerrarModal() {
      this.modal.open = false
      this.modal.name = null
      this.modal.payload = null
    },

    abrirModalRenombrar(item) {
      const objetivo = item ?? this.itemsSeleccionados[0]
      if (!objetivo) return
      this.abrirModal('renombrar', objetivo)
    },

    abrirModalMover(item) {
      const items = item ? [item] : this.itemsSeleccionados
      if (!items.length) return
      this.abrirModal('mover', { ids: items.map((i) => i.id) })
    },

    async abrirModalPrevisualizar(item) {
      try {
        const { url } = await apiItems.previsualizar(item.id)
        this.abrirModal('previsualizar', { item, url })
      } catch (e) {
        this.agregarNotificacion({
          id: 'preview-error',
          tipo: 'error',
          mensaje: mensajeDeAccion(e, 'No se pudo previsualizar el archivo.'),
          icono: 'pi-eye-slash',
        })
      }
    },

    // === ESPACIO =============================================

    async cargarEspacio() {
      try {
        const antes = this.espacio
        this.espacio = await apiItems.espacio()
        // Como Nextcloud: avisa al entrar ya lleno o al pasar de tener sitio a no tenerlo
        if (this.espacio.libre === 0 && this.espacio.cuota > 0 && (!antes || antes.libre > 0)) {
          this.agregarNotificacion({
            id: 'espacio-lleno',
            tipo: 'error',
            mensaje: 'Tu almacenamiento está lleno: no puedes subir más archivos.',
            icono: 'pi-cloud',
          })
        }
      } catch (error) {
        console.error('No se pudo cargar el espacio:', error)
      }
    },

    // Antes de subir, con la cifra recién pedida; si no se puede saber, decide el servidor
    async motivoSinEspacio(ficheros) {
      await this.cargarEspacio()
      if (!this.espacio) return null
      const { libre, limite_fichero: limite } = this.espacio
      const grande = ficheros.find((f) => f.size > limite)
      if (grande) return `"${grande.name}" supera el máximo de ${formatBytes(limite)} por fichero.`
      const total = ficheros.reduce((suma, f) => suma + f.size, 0)
      if (total > libre) {
        const verbo = ficheros.length === 1 ? 'ocupa' : 'ocupan'
        return `No hay espacio: ${verbo} ${formatBytes(total)} y quedan ${formatBytes(libre)} libres.`
      }
      return null
    },

    // === NOTIFICACIONES ======================================

    agregarNotificacion({ id, tipo, mensaje, icono, severidad = 'neutro' }) {
      //Evita duplicados: si ya existe una notificación con ese id, la borramos primero
      this.eliminarNotificacion(id)

      const nuevaNotificacion = { id, tipo, mensaje, icono, severidad, timerId: null }
      this.notificaciones.push(nuevaNotificacion)

      // Las de éxito y error se cierran solas pasados unos segundos
      const seCierraAutomaticamente = tipo === 'exito' || tipo === 'error'

      if (seCierraAutomaticamente) {
        const segundos = tipo === 'error' ? NOTIF_DURACION_ERROR : NOTIF_DURACION_EXITO
        const notif = this.notificaciones.find((n) => n.id === id)

        // Guardamos el id del temporizador para poder cancelarlo si hace falta
        notif.timerId = setTimeout(() => this.eliminarNotificacion(id), segundos * 1000)
      }
    },

    actualizarNotificacion(id, cambios, autoCloseSeg = 3) {
      const notif = this.notificaciones.find((n) => n.id === id)
      if (!notif) return

      // Cancelamos el temporizador anterior para no cerrar la notificación antes de tiempo
      if (notif.timerId) clearTimeout(notif.timerId)

      // Aplicamos los cambios encima de la notificación existente
      Object.assign(notif, cambios)

      // Si el nuevo tipo es éxito o error, arrancamos un nuevo temporizador de cierre
      const seCierraAutomaticamente = cambios.tipo === 'exito' || cambios.tipo === 'error'
      if (seCierraAutomaticamente) {
        const segundos = cambios.tipo === 'error' ? NOTIF_DURACION_ERROR : autoCloseSeg
        notif.timerId = setTimeout(() => this.eliminarNotificacion(id), segundos * 1000)
      }
    },

    eliminarNotificacion(id) {
      const indice = this.notificaciones.findIndex((n) => n.id === id)
      if (indice === -1) return

      // Cancelamos el temporizador antes de eliminarla para que no intente borrar una notificación que ya no existe
      const notif = this.notificaciones[indice]
      if (notif.timerId) clearTimeout(notif.timerId)

      this.notificaciones.splice(indice, 1)
    },


    // === ITEMS (Lectura) ====================================

    recargar() {
      return this.cargarItems(this.currentParams)
    },

    async cargarItems(params = {}) {
      // Uso un token para poder ignorar respuestas de peticiones antiguas.
      // Ej. Un usuario navega a otra carpeta antes de que llegara la información de la primera query.
      const token = ++this.loadToken
      this.loading = true
      this.currentParams = { ...params }
      try {
        const data = await apiItems.listar(params)
        if (token !== this.loadToken) return
        this.items = data.items
        this.breadcrumb = data.breadcrumb || []
      } catch (error) {
        if (token === this.loadToken) {
          this.agregarNotificacion({
            id: 'cargar-error',
            tipo: 'error',
            mensaje: mensajeDeAccion(error, 'No se pudieron cargar los archivos'),
            icono: 'pi-folder-open',
          })
        }
      } finally {
        if (token === this.loadToken) this.loading = false
      }
    },

    async buscarItems(q) {
      this.loading = true
      this.queryBusqueda = q
      this.limpiarSeleccion()
      try {
        const data = await apiItems.buscar(q)
        this.items = data.items
        this.breadcrumb = []
      } catch (error) {
        this.items = []
        this.agregarNotificacion({
          id: 'buscar-error',
          tipo: 'error',
          mensaje: mensajeDeAccion(error, 'Error al realizar la búsqueda'),
          icono: 'pi-search',
        })
      } finally {
        this.loading = false
      }
    },

    // === Items (Escritura) =====================================

    // Formulario: devuelve el error para enseñarlo debajo de la caja (null si fue bien)
    async crearCarpeta(data) {
      try {
        await apiItems.crearCarpeta(data)
        return null
      } catch (error) {
        console.error(error)
        return getErrorMessage(error) || 'No se pudo crear la carpeta'
      }
    },

    // Sube un archivo usando una url presignada de 3 pasos:
    // 1. Pide al backend una URL temporal para subir directamente al bucket
    // 2. Sube los bytes directo al bucket (sin pasar por el servidor)
    // 3. Notifica al backend para que registre el archivo en la base de datos
    async _subirArchivoPresignado(file, padreId) {
      const mimeType = file.type || 'application/octet-stream'
      const { url_subida, key } = await apiItems.solicitarSubida(file.name, mimeType, file.size)
      await apiItems.subirDirecto(url_subida, file, mimeType)
      await apiItems.confirmarSubida(file.name, key, padreId, mimeType)
    },

    // Abre el selector del sistema (un archivo o una carpeta) y sube lo elegido a padreId
    elegirYSubir(tipo, padreId = null) {
      const input = document.createElement('input')
      input.type = 'file'
      input.hidden = true
      input.webkitdirectory = tipo === 'carpeta'
      input.addEventListener('change', () => {
        const files = Array.from(input.files)
        input.remove()
        if (!files.length) return
        if (tipo === 'carpeta') this.subirCarpeta(files, padreId)
        else this.subirArchivo(files[0], padreId)
      })
      input.addEventListener('cancel', () => input.remove())
      document.body.appendChild(input)
      input.click()
    },

    async subirArchivo(file, padreId = null) {
      const motivo = await this.motivoSinEspacio([file])
      if (motivo) {
        this.agregarNotificacion({ id: 'subir-error', tipo: 'error', mensaje: motivo, icono: 'pi-cloud' })
        return
      }
      this.agregarNotificacion({
        id: 'subir',
        tipo: 'cargando',
        mensaje: 'Subiendo archivo…',
        icono: 'pi-upload',
        severidad: 'neutro',
      })
      try {
        await this._subirArchivoPresignado(file, padreId)
        await this.cargarItems(this.currentParams)
      } catch (error) {
        this.agregarNotificacion({
          id: 'subir-error',
          tipo: 'error',
          mensaje: mensajeDeAccion(error, 'No se pudo subir el archivo'),
          icono: 'pi-upload',
        })
      } finally {
        this.eliminarNotificacion('subir')
        await this.cargarEspacio()
      }
    },

    //Lo necesitamos para subir carpetas enteras con sus archivos
    _parsearEstructuraCarpeta(files) {
      const IGNORADOS = new Set(['.DS_Store', 'Thumbs.db', 'desktop.ini', '.localized'])
      const carpetas = new Set()
      const archivos = []

      for (const file of files) {
        if (IGNORADOS.has(file.name)) continue

        const ruta = rutaRelativa(file)
        const partes = ruta.split('/')

        // Añade todos los segmentos intermedios como carpetas a crear
        // i empieza en 1 para saltarse la carpeta raíz, que ya existe en el destino
        for (let i = 1; i < partes.length; i++) {
          carpetas.add(partes.slice(0, i).join('/'))
        }

        archivos.push({ file, rutaRelativa: ruta })
      }

      // Ordena por número de '/' para que los padres se creen antes que los hijos
      // Por las restricciones no se pueden crear los hijos antes que los padres
      const carpetasOrdenadas = Array.from(carpetas).sort(
        (a, b) => a.split('/').length - b.split('/').length
      )

      return { carpetasOrdenadas, archivos }
    },

    // Lo soltado desde el ordenador (ficheros, carpetas o mezcla) sigue el camino de "Subir carpeta"
    async subirSoltados(evento, padreId = null) {
      // fromEvent lee lo soltado antes del primer await: Chrome lo vacía después
      const files = await fromEvent(evento)
      await this.subirCarpeta(files, padreId)
    },

    async subirCarpeta(files, padreId = null) {
      if (!files.length) return

      const NOTIF_ID = 'subir-carpeta'
      //Para subir de 3 en 3
      const LOTE = 3

      // Si no cabe entera, no se sube nada: mejor que dejar una carpeta a medias
      const { carpetasOrdenadas, archivos } = this._parsearEstructuraCarpeta(files)
      if (!archivos.length) return
      const motivo = await this.motivoSinEspacio(archivos.map((a) => a.file))
      if (motivo) {
        this.agregarNotificacion({ id: NOTIF_ID, tipo: 'error', mensaje: motivo, icono: 'pi-cloud', severidad: 'peligro' })
        return
      }

      this.agregarNotificacion({
        id: NOTIF_ID,
        tipo: 'cargando',
        mensaje: 'Preparando la subida…',
        icono: 'pi-folder',
        severidad: 'neutro',
      })

      try {
        // Con solo ficheros sueltos no hay carpetas que crear (el backend no acepta la lista vacía)
        let mapa = {}
        if (carpetasOrdenadas.length) {
          this.actualizarNotificacion(NOTIF_ID, {
            mensaje: `Creando ${carpetasOrdenadas.length} carpeta${carpetasOrdenadas.length !== 1 ? 's' : ''}…`,
          })
          ;({ mapa } = await apiItems.crearArbolCarpetas(carpetasOrdenadas, padreId))
        }

        let subidos = 0
        let fallidos = 0
        let primerFallo = null
        const total = archivos.length

        this.actualizarNotificacion(NOTIF_ID, { mensaje: `Subiendo archivos… 0 / ${total}` })

        for (let i = 0; i < archivos.length; i += LOTE) {
          const lote = archivos.slice(i, i + LOTE)
          //Usamos allSettled porque lanza todas las promesas a la vez y nos evita que si una falla se aborte la subida
          const resultados = await Promise.allSettled(
            lote.map(async ({ file, rutaRelativa }) => {
              const partes = rutaRelativa.split('/')
              const rutaPadre = partes.slice(0, -1).join('/')
              const padreArchivo = mapa[rutaPadre] ?? padreId
              await this._subirArchivoPresignado(file, padreArchivo)
            })
          )

          for (const resultado of resultados) {
            if (resultado.status === 'fulfilled') {
              subidos++
            } else {
              fallidos++
              primerFallo ??= resultado.reason
              console.error('Error subiendo archivo:', resultado.reason?.response?.data ?? resultado.reason)
            }
          }

          this.actualizarNotificacion(NOTIF_ID, {
            mensaje: `Subiendo archivos… ${subidos + fallidos} / ${total}`,
          })
        }

        if (fallidos === 0) {
          this.actualizarNotificacion(
            NOTIF_ID,
            {
              tipo: 'exito',
              mensaje: `${carpetasOrdenadas.length ? 'Carpeta subida correctamente' : 'Subida completada'} (${subidos} archivo${subidos !== 1 ? 's' : ''})`,
              icono: 'pi-check',
              severidad: 'neutro',
            },
            3,
          )
        } else {
          const motivo = motivoParaUsuario(primerFallo)
          this.actualizarNotificacion(
            NOTIF_ID,
            {
              tipo: 'error',
              mensaje: `${subidos} subidos, ${fallidos} fallaron` + (motivo ? `: ${motivo}` : ''),
              icono: 'pi-exclamation-triangle',
              severidad: 'advertencia',
            },
            5,
          )
        }

      } catch (error) {
        this.actualizarNotificacion(
          NOTIF_ID,
          {
            tipo: 'error',
            mensaje: mensajeDeAccion(error, 'Error al crear la estructura de carpetas'),
            icono: 'pi-times',
            severidad: 'peligro',
          },
          5,
        )
      } finally {
        await this.cargarItems(this.currentParams)
        await this.cargarEspacio()
      }
    },

    // Formulario: devuelve el error para enseñarlo debajo de la caja (null si fue bien)
    async renombrarItem(id, nombre) {
      try {
        const { nombre: nombreGuardado } = await apiItems.renombrar(id, nombre)
        this.actualizarItemsLocal([id], { nombre: nombreGuardado })
        this.agregarNotificacion({
          id: 'renombrar',
          tipo: 'exito',
          mensaje: 'Elemento renombrado',
          icono: 'pi-pencil',
          severidad: 'neutro',
        })
        return null
      } catch (error) {
        console.error(error)
        return getErrorMessage(error) || 'No se pudo renombrar el elemento'
      }
    },

    //Lo usamos para reflejar un cambio en la UI de forma inmediata. 
    // Ejemplo: Pinto la estrella de favorito sin necesidad de recargar todo el servidor
    actualizarItemsLocal(ids, cambios) {
      const set = new Set(ids)
      this.items = this.items.map((item) =>
        set.has(item.id) ? { ...item, ...cambios } : item
      )
    },

    // Devuelve si se movió, para que pegar sepa si vaciar el portapapeles
    async moverItems(ids, destinoId) {
      try {
        await apiItems.mover(ids, destinoId)
        if (destinoId !== this.carpetaAbiertaId) {
          this.items = this.items.filter((item) => !ids.includes(item.id))
        }
        this.limpiarSeleccion()
        this.agregarNotificacion({
          id: 'mover',
          tipo: 'exito',
          mensaje: ids.length === 1 ? 'Elemento movido' : `${ids.length} elementos movidos`,
          icono: 'pi-arrow-right',
          severidad: 'neutro',
        })
        return true
      } catch (error) {
        this.agregarNotificacion({
          id: 'mover',
          tipo: 'error',
          mensaje: mensajeDeAccion(error, 'No se pudo mover el elemento'),
          icono: 'pi-times',
        })
        return false
      }
    },

    // === CORTAR, COPIAR Y PEGAR =================================

    guardarEnPortapapeles(modo) {
      const items = this.itemsSeleccionados
      if (!items.length) return
      this.portapapeles = { ids: items.map((i) => i.id), padres: items.map((i) => i.padre ?? null), modo }
    },

    vaciarPortapapeles() {
      this.portapapeles = { ids: [], padres: [], modo: null }
    },

    // Lo mismo que evita el arrastre: ni dentro de sí misma ni donde ya está
    motivoNoPegar(destinoId) {
      const { ids, padres, modo } = this.portapapeles
      const ruta = new Set(this.breadcrumb.map((n) => n.id).filter((id) => id !== null))
      if (destinoId !== null) ruta.add(destinoId)
      if (ids.some((id) => ruta.has(id))) return 'Una carpeta no puede ir dentro de sí misma'
      if (modo === 'cortar' && padres.every((p) => p === destinoId)) return 'Ya está en esta carpeta'
      return null
    },

    async pegar(destinoId) {
      if (!this.portapapeles.ids.length) return
      const motivo = this.motivoNoPegar(destinoId)
      if (motivo) {
        this.agregarNotificacion({ id: 'pegar', tipo: 'error', mensaje: motivo, icono: 'pi-clipboard' })
        return
      }
      if (this.portapapeles.modo === 'copiar') {
        await this.copiarItems(this.portapapeles.ids, destinoId)
      } else if (await this.moverItems(this.portapapeles.ids, destinoId)) {
        this.vaciarPortapapeles()
        await this.recargar()
      }
    },

    // Lo copiado se queda en el portapapeles: se puede pegar más veces
    async copiarItems(ids, destinoId) {
      this.agregarNotificacion({ id: 'pegar', tipo: 'cargando', mensaje: 'Copiando…', icono: 'pi-copy' })
      try {
        const { copiados } = await apiItems.copiar(ids, destinoId)
        this.actualizarNotificacion('pegar', {
          tipo: 'exito',
          mensaje: copiados === 1 ? 'Elemento copiado' : `${copiados} elementos copiados`,
          icono: 'pi-check',
        })
        await this.recargar()
      } catch (error) {
        this.actualizarNotificacion('pegar', {
          tipo: 'error',
          mensaje: mensajeDeAccion(error, 'No se pudo copiar'),
          icono: 'pi-times',
        }, 5)
      } finally {
        await this.cargarEspacio()
      }
    },

    // Si la fila no estaba seleccionada, se mueve solo ella (como en el Finder)
    empezarArrastre(item, index) {
      if (!this.seleccion.ids.includes(item.id)) this.seleccionar(item, index)
      this.arrastre.ids = [...this.seleccion.ids]
    },

    marcarDestinoArrastre(destino, motivo) {
      if (this.arrastre.destino?.id !== destino?.id) this.arrastre.destino = destino
      this.arrastre.motivo = motivo
    },

    limpiarArrastre() {
      this.arrastre = { ids: [], destino: null, motivo: null }
    },

    async marcarFavoritos(ids = []) {
      const id = ids[0]
      try {
        const { favorito: nuevoFavorito } = await apiItems.marcarFavorito(id)
        if (!nuevoFavorito && this.currentParams.favorito === 'true') {
          this.items = this.items.filter((item) => item.id !== id)
        } else {
          this.actualizarItemsLocal([id], { favorito: nuevoFavorito })
        }
        this.limpiarSeleccion()
      } catch (error) {
        this.agregarNotificacion({
          id: 'favorito-error',
          tipo: 'error',
          mensaje: mensajeDeAccion(error, 'No se pudo actualizar el favorito'),
          icono: 'pi-star',
        })
      }
    },

    // === Papelera y Eliminación ============================================

    async eliminarItems(ids = []) {
      try {
        await apiItems.moverAPapelera(ids)
        this.items = this.items.filter((item) => !ids.includes(item.id))
        this.limpiarSeleccion()
        this.agregarNotificacion({
          id: 'papelera',
          tipo: 'exito',
          mensaje: 'Movido a la papelera',
          icono: 'pi-trash',
          severidad: 'neutro',
        })
      } catch (error) {
        this.agregarNotificacion({
          id: 'papelera-error',
          tipo: 'error',
          mensaje: mensajeDeAccion(error, 'No se pudo mover a la papelera'),
          icono: 'pi-trash',
        })
      }
    },

    async eliminarDefinitivamente(ids = []) {
      this.agregarNotificacion({
        id: 'eliminar',
        tipo: 'cargando',
        mensaje: 'Eliminando archivos de S3…',
        icono: 'pi-times-circle',
        severidad: 'neutro',
      })
      try {
        await apiItems.eliminarDefinitivo(ids)
        this.items = this.items.filter((item) => !ids.includes(item.id))
        this.limpiarSeleccion()
        this.actualizarNotificacion(
          'eliminar',
          { tipo: 'exito', mensaje: 'Eliminado definitivamente', icono: 'pi-check-circle' },
          3,
        )
      } catch (error) {
        this.actualizarNotificacion('eliminar', { tipo: 'error', mensaje: mensajeDeAccion(error, 'Error al eliminar') }, 5)
      } finally {
        await this.cargarEspacio()
      }
    },

    async restaurarItems(ids = []) {
      try {
        await apiItems.restaurar(ids)
        this.items = this.items.filter((item) => !ids.includes(item.id))
        this.limpiarSeleccion()
        this.agregarNotificacion({
          id: 'restaurar',
          tipo: 'exito',
          mensaje: 'Elemento restaurado',
          icono: 'pi-replay',
          severidad: 'neutro',
        })
      } catch (error) {
        this.agregarNotificacion({
          id: 'restaurar-error',
          tipo: 'error',
          mensaje: mensajeDeAccion(error, 'No se pudo restaurar el elemento'),
          icono: 'pi-replay',
        })
      }
    },

    async restaurarPapelera() {
      try {
        await apiItems.restaurarTodo()
        await this.cargarItems(this.currentParams)
        this.agregarNotificacion({
          id: 'restaurar',
          tipo: 'exito',
          mensaje: 'Papelera restaurada',
          icono: 'pi-replay',
          severidad: 'neutro',
        })
      } catch (error) {
        this.agregarNotificacion({
          id: 'restaurar-error',
          tipo: 'error',
          mensaje: mensajeDeAccion(error, 'No se pudo restaurar la papelera'),
          icono: 'pi-replay',
        })
      }
    },

    async vaciarPapelera() {
      this.agregarNotificacion({
        id: 'vaciar-papelera',
        tipo: 'cargando',
        mensaje: 'Vaciando papelera…',
        icono: 'pi-trash',
        severidad: 'neutro',
      })
      try {
        await apiItems.vaciarPapelera()
        await this.cargarItems(this.currentParams)
        this.actualizarNotificacion(
          'vaciar-papelera',
          { tipo: 'exito', mensaje: 'Papelera vaciada', icono: 'pi-check-circle' },
          3,
        )
      } catch (error) {
        this.actualizarNotificacion(
          'vaciar-papelera',
          { tipo: 'error', mensaje: mensajeDeAccion(error, 'Error al vaciar la papelera') },
          5,
        )
      } finally {
        await this.cargarEspacio()
      }
    },

    // === DESCARGAR ==============================================================

    // Un fichero suelto: lo usan la selección y el visor de PDF
    async descargarArchivo(item) {
      try {
        const { url } = await apiItems.descargarArchivo(item.id)
        const a = document.createElement('a')
        a.href = url
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
      } catch (error) {
        this.agregarNotificacion({
          id: 'descargar-error',
          tipo: 'error',
          mensaje: mensajeDeAccion(error, 'No se pudo descargar el archivo'),
          icono: 'pi-download',
        })
      }
    },

    async descargarItems() {
      const seleccion = this.itemsSeleccionados
      if (!seleccion.length) return

      if (seleccion.length === 1 && seleccion[0].tipo === 'archivo') {
        await this.descargarArchivo(seleccion[0])
        return
      }

      this.agregarNotificacion({
        id: 'descargar',
        tipo: 'cargando',
        mensaje: 'Comprimiendo archivos…',
        icono: 'pi-download',
        severidad: 'neutro',
      })
      try {
        const ids = seleccion.map((i) => i.id)
        const nombre = seleccion.length === 1 ? `${seleccion[0].nombre}.zip` : 'descarga.zip'
        const blob = await apiItems.descargarZip(ids)
        const blobUrl = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = blobUrl
        a.download = nombre
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(blobUrl)
      } catch (error) {
        // Con responseType 'blob' el error llega como Blob: se lee para no perder el motivo ni la ref
        if (error?.response?.data instanceof Blob) {
          try { error.response.data = JSON.parse(await error.response.data.text()) } catch { /* no es JSON */ }
        }
        const mensaje = error?.response?.status === 404
          ? 'La carpeta no contiene ningún archivo'
          : mensajeDeAccion(error, 'No se pudo generar la descarga')
        this.agregarNotificacion({
          id: 'descargar-error',
          tipo: 'error',
          mensaje,
          icono: 'pi-download',
        })
      } finally {
        this.eliminarNotificacion('descargar')
      }
    },

    // === VERSIONES (solo audio) =====================================================
    
    //Esto lo usamos para poder subir nuevas versiones de canciones
    async subirNuevaVersion(file, itemId) {
      const NOTIF_ID = `version-${itemId}`
      const motivo = await this.motivoSinEspacio([file])
      if (motivo) {
        this.agregarNotificacion({ id: NOTIF_ID, tipo: 'error', mensaje: motivo, icono: 'pi-cloud' })
        return false
      }
      this.agregarNotificacion({
        id: NOTIF_ID,
        tipo: 'cargando',
        mensaje: 'Subiendo nueva versión…',
        icono: 'pi-upload',
        severidad: 'neutro',
      })
      try {
        const mimeType = file.type || 'application/octet-stream'
        const { url_subida, key } = await apiItems.solicitarSubidaVersion(itemId, file.size)
        await apiItems.subirDirecto(url_subida, file, mimeType)
        const itemActualizado = await apiItems.confirmarSubidaVersion(itemId, key, mimeType)
        this.actualizarItemsLocal([itemId], itemActualizado)
        this.actualizarNotificacion(NOTIF_ID, {
          tipo: 'exito',
          mensaje: 'Nueva versión subida correctamente',
          icono: 'pi-check',
          severidad: 'neutro',
        })
        return true
      } catch (e) {
        this.actualizarNotificacion(NOTIF_ID, {
          tipo: 'error',
          mensaje: mensajeDeAccion(e, 'No se pudo subir la nueva versión'),
          icono: 'pi-times',
        }, 5)
        return false
      } finally {
        await this.cargarEspacio()
      }
    },

    // === SELECCIONADOS ============================================================

    seleccionar(item, index) {
      this.seleccion.ids = [item.id]
      this.seleccion.lastIndex = index
      if (this.panelInfo.visible) this.panelInfo.itemId = item.id
    },

    toggleSeleccion(item, index) {
      const ya = this.seleccion.ids.includes(item.id)
      if (ya) {
        this.seleccion.ids = this.seleccion.ids.filter((id) => id !== item.id)
      } else {
        this.seleccion.ids = [...this.seleccion.ids, item.id]
      }
      this.seleccion.lastIndex = index
    },

    seleccionarRango(index, itemsVisibles) {
      if (this.seleccion.lastIndex === null) return
      const desde = Math.min(this.seleccion.lastIndex, index)
      const hasta = Math.max(this.seleccion.lastIndex, index)
      const rango = itemsVisibles.slice(desde, hasta + 1).map((i) => i.id)
      const merged = new Set([...this.seleccion.ids, ...rango])
      this.seleccion.ids = [...merged]
    },

    limpiarSeleccion() {
      this.seleccion.ids = []
      this.seleccion.lastIndex = null
      if (this.panelInfo.visible) this.cerrarPanelInfo()
    },
  },
})
