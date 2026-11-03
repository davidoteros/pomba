import axios from 'axios'
import api from './axios'

export const apiItems = {

  async listar(params = {}) {
    const { data } = await api.get('items/', { params })
    return data
  },

  async buscar(q) {
    const { data } = await api.get('items/buscar/', { params: { q } })
    return data
  },

  async crearCarpeta(datos) {
    const { data } = await api.post('items/', datos)
    return data
  },

  async renombrar(id, nombre) {
    await api.post(`items/${id}/renombrar/`, { nombre })
  },

  // Pide al backend que genere una URL presignada para subir directamente al bucket.
  // Devuelve { url_subida, key } donde key es la ruta del objeto en el bucket.
  // El tamaño va aquí porque el backend comprueba la cuota antes de firmar la URL.
  async solicitarSubida(nombre, mimeType, tamanoBytes) {
    const { data } = await api.post('items/solicitar_subida/', {
      nombre,
      mime_type: mimeType,
      tamano_bytes: tamanoBytes,
    })
    return data
  },

  async subirDirecto(urlSubida, file, mimeType) {
    await axios.put(urlSubida, file, { headers: { 'Content-Type': mimeType } })
  },

  // El tamaño no se manda: el backend lo lee de Garage al confirmar (head_object).
  async confirmarSubida(nombre, key, padreId, mimeType) {
    await api.post('items/confirmar_subida/', {
      nombre,
      key,
      padre: padreId,
      mime_type: mimeType,
    })
  },

  async crearArbolCarpetas(rutas, padreId) {
    const { data } = await api.post('items/crear_arbol_carpetas/', { rutas, padre: padreId })
    return data
  },

  async mover(ids, destinoId) {
    await api.post('items/mover/', { ids, destino: destinoId })
  },

  async marcarFavorito(id) {
    const { data } = await api.post('items/favorito/', { id })
    return data
  },

  async moverAPapelera(ids) {
    await api.post('items/trash/', { ids })
  },

  async restaurar(ids) {
    await api.post('items/restaurar/', { ids })
  },

  async restaurarTodo() {
    await api.post('items/restaurar_papelera/')
  },

  async vaciarPapelera() {
    await api.post('items/vaciar_papelera/')
  },

  async eliminarDefinitivo(ids) {
    await api.delete('items/eliminar_definitivo/', { data: { ids } })
  },

  async descargarArchivo(id) {
    const { data } = await api.get(`items/${id}/descargar_archivo/`)
    return data
  },

  async previsualizar(id) {
    const { data } = await api.get(`items/${id}/previsualizar/`)
    return data
  },

  async descargarZip(ids) {
    const { data } = await api.post('items/descargar/', { ids }, { responseType: 'blob' })
    return data
  },

  // === Versiones (solo audio de momento) ================================

  async listarVersiones(itemId) {
    const { data } = await api.get(`items/${itemId}/versiones/`)
    return data
  },

  async solicitarSubidaVersion(itemId, tamanoBytes) {
    const { data } = await api.post(`items/${itemId}/versiones/solicitar_subida/`, {
      tamano_bytes: tamanoBytes,
    })
    return data
  },

  async confirmarSubidaVersion(itemId, key, mimeType) {
    const { data } = await api.post(`items/${itemId}/versiones/confirmar_subida/`, {
      key,
      mime_type: mimeType,
    })
    return data
  },

  async descargarVersion(itemId, numero) {
    const { data } = await api.get(`items/${itemId}/versiones/${numero}/descargar/`)
    return data
  },

  async activarVersion(itemId, numero) {
    const { data } = await api.post(`items/${itemId}/versiones/${numero}/activar/`)
    return data
  },

  async eliminarVersion(itemId, numero) {
    await api.delete(`items/${itemId}/versiones/${numero}/`)
  },

  async previsualizarVersion(itemId, numero) {
    const { data } = await api.get(`items/${itemId}/versiones/${numero}/previsualizar/`)
    return data
  },
}
