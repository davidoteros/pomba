<script setup>
import { ref, computed, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useGestorItems } from '@/stores/items'
import { useConfirmacion } from '@/composables/useConfirmacion'
import { formatDate } from '../utils/date'
import { formatBytes } from '../utils/bytes'
import { obtenerIcono } from '../utils/iconos'

const gestor = useGestorItems()
const { confirmar } = useConfirmacion()
//Por defecto
const sortCampo = ref('fecha_modificacion')
const sortDir = ref('desc')

function ordenarPor(campo) {
  if (sortCampo.value === campo) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortCampo.value = campo
    sortDir.value = 'asc'
  }
}

const comparadores = {
  //Uso base, para que ignore mayúsculas y minúsculas
  nombre: (a, b) => a.nombre.localeCompare(b.nombre, 'es', { sensitivity: 'base' }),
  tamano_bytes: (a, b) => (a.tamano_bytes ?? -1) - (b.tamano_bytes ?? -1),
  fecha_modificacion: (a, b) => new Date(a.fecha_modificacion) - new Date(b.fecha_modificacion),
}

const itemsOrdenados = computed(() => {
  // 1 si ascendente, -1 si descendente (multiplicamos para invertir orden)
  const dir = sortDir.value === 'asc' ? 1 : -1
  // coge la función de comparación según la columna activa (nombre, fecha, tamaño...)
  const comparar = comparadores[sortCampo.value]
  // copia el array para no mutar gestor.items y ordena aplicando la dirección
  return [...gestor.items].sort((a, b) => dir * comparar(a, b))
})

const route = useRoute()
const router = useRouter()

const emit = defineEmits(['rename', 'move'])

const menuAbierto = ref(null)

//Query al navegador para saber si es movil/tablet o desktop (Esto define el tipo de click)
const esTactil = window.matchMedia('(pointer: coarse)').matches
const enPapelera = computed(() => (route.params.view || 'drive') === 'trash')

function abrirItem(item) {
  if (item.tipo !== 'carpeta') return
  router.push({
    name: 'home',
    params: { view: route.params.view || 'drive', folderId: item.id },
  })
}

function esPrevisualizableItem(item) {
  // El backend decide qué se puede abrir inline (campo previsualizable).
  return item.tipo === 'archivo' && item.previsualizable === true
}

function handleClick(event, item, index) {
  if (contextMenu.value.visible) contextMenu.value.visible = false

  if (menuAbierto.value !== null) {
    menuAbierto.value = null
    return
  }

  if (esTactil) {
    gestor.limpiarSeleccion()
    abrirItem(item)
    return
  }

  if (event.shiftKey && gestor.seleccion.lastIndex !== null) {
    gestor.seleccionarRango(index, itemsOrdenados.value)
    return
  }
  if (event.ctrlKey || event.metaKey) {
    gestor.toggleSeleccion(item, index)
    return
  }
  if (gestor.seleccion.ids.length === 1 && gestor.seleccion.ids[0] === item.id) {
    gestor.limpiarSeleccion()
    return
  }
  gestor.seleccionar(item, index)
}

function handleDoubleClick(item) {
  if (window.matchMedia('(pointer: coarse)').matches) return
  gestor.limpiarSeleccion()
  if (item.tipo === 'carpeta') {
    abrirItem(item)
  } else if (esPrevisualizableItem(item) && !enPapelera.value) {
    gestor.abrirModalPrevisualizar(item)
  }
}

function handleBackgroundClick(event) {
  if (event.target === event.currentTarget) {
    gestor.limpiarSeleccion()
    menuAbierto.value = null
  }
}

// === Lógica compartida de acciones ==============================
async function ejecutarAccion(accion, item) {
  if (accion === 'info') {
    gestor.abrirPanelInfo(item)
  } else if (accion === 'preview') {
    await gestor.abrirModalPrevisualizar(item)
  } else if (accion === 'download') {
    gestor.seleccionar(item, null)
    await gestor.descargarItems()
  } else if (accion === 'favorite' || accion === 'unfavorite') {
    await gestor.marcarFavoritos([item.id])
  } else if (accion === 'delete') {
    await gestor.eliminarItems([item.id])
  } else if (accion === 'restore') {
    await gestor.restaurarItems([item.id])
  } else if (accion === 'deleteForever') {
    const ok = await confirmar({
      header: '¿Eliminar definitivamente?',
      mensaje: 'Esta acción no se puede deshacer.',
      labelAceptar: 'Eliminar',
      peligro: true,
    })
    if (ok) await gestor.eliminarDefinitivamente([item.id])
  } else {
    emit(accion, item)
  }
}

// === Menú ··· ==================================================
function toggleMenu(event, itemId) {
  event.stopPropagation()
  menuAbierto.value = menuAbierto.value === itemId ? null : itemId
}

async function accionMenu(event, accion, item) {
  event.stopPropagation()
  menuAbierto.value = null
  await ejecutarAccion(accion, item)
}

// === Context menu (click derecho) ===============================
const contextMenu = ref({ visible: false, x: 0, y: 0, item: null, vacio: false })

// Crear y subir solo tienen sentido en Mi unidad (no en favoritos, recientes, papelera ni búsqueda)
const enMiUnidad = computed(() => route.name === 'home' && (route.params.view || 'drive') === 'drive')

function abrirMenu(event, item, vacio) {
  event.preventDefault()
  menuAbierto.value = null

  const MENU_W = 176
  const MENU_H = vacio ? 130 : 230
  const x = event.clientX + MENU_W > window.innerWidth ? event.clientX - MENU_W : event.clientX
  const y = event.clientY + MENU_H > window.innerHeight ? event.clientY - MENU_H : event.clientY

  contextMenu.value = { visible: true, x, y, item, vacio }
}

function handleContextMenu(event, item, index) {
  if (!gestor.seleccion.ids.includes(item.id)) {
    gestor.seleccionar(item, index)
  }
  abrirMenu(event, item, false)
}

// Clic derecho en un hueco: nueva carpeta o subir en la carpeta abierta
function handleContextMenuVacio(event) {
  if (!enMiUnidad.value) return
  gestor.limpiarSeleccion()
  abrirMenu(event, null, true)
}

function carpetaActual() {
  return route.params.folderId ? Number(route.params.folderId) : null
}

// === Soltar ficheros del ordenador (subir) ======================
const arrastrando = ref(false)
const destinoSoltar = ref(null)
// Rectángulo visible de la lista: el marco va encima para que la cabecera fija no lo tape
const marcoSoltar = ref(null)
let apagarArrastre = null

// Solo ficheros que vienen de fuera del navegador, no texto ni enlaces
function traeFicheros(event) {
  return event.dataTransfer?.types.includes('Files')
}

// La carpeta de la fila bajo el ratón; null si es un hueco o un archivo
function carpetaBajo(event) {
  const fila = event.target.closest?.('[data-carpeta-id]')
  return fila ? gestor.items.find((i) => i.id === Number(fila.dataset.carpetaId)) ?? null : null
}

const nombreDestino = computed(() => {
  if (destinoSoltar.value) return destinoSoltar.value.nombre
  if (!route.params.folderId) return 'Mi unidad'
  return gestor.breadcrumb.at(-1)?.label ?? 'esta carpeta'
})

function handleDragOver(event) {
  if (!enMiUnidad.value || !traeFicheros(event)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'copy'
  if (!arrastrando.value) {
    const { top, left, width, height } = event.currentTarget.parentElement.getBoundingClientRect()
    marcoSoltar.value = { top: `${top}px`, left: `${left}px`, width: `${width}px`, height: `${height}px` }
  }
  arrastrando.value = true
  destinoSoltar.value = carpetaBajo(event)
  // Firefox a veces no avisa de que el ratón ha salido: se apaga solo si deja de llegar dragover
  clearTimeout(apagarArrastre)
  apagarArrastre = setTimeout(terminarArrastre, 3000)
}

// Pasar de una fila a otra también lanza dragleave: solo cuenta si sale de la zona
function handleDragLeave(event) {
  if (event.currentTarget.contains(event.relatedTarget)) return
  terminarArrastre()
}

function terminarArrastre() {
  clearTimeout(apagarArrastre)
  arrastrando.value = false
  destinoSoltar.value = null
}

function handleDrop(event) {
  if (!enMiUnidad.value || !traeFicheros(event)) return
  event.preventDefault()
  const padre = carpetaBajo(event)?.id ?? carpetaActual()
  terminarArrastre()
  gestor.subirSoltados(event, padre)
}

// === Mover arrastrando dentro de Pomba ==========================
const CLASE_DESTINO = 'bg-primary/30! ring-2 ring-inset ring-primary'
const vistaArrastre = ref(null)
const puedeArrastrar = computed(() => !esTactil && enMiUnidad.value)

const queSeMueve = computed(() => {
  const { ids } = gestor.arrastre
  if (ids.length !== 1) return `${ids.length} elementos`
  return gestor.items.find((i) => i.id === ids[0])?.nombre ?? '1 elemento'
})


function prepararVistaArrastre(item) {
  const { ids } = gestor.arrastre
  const [icono, nombre, cuenta] = vistaArrastre.value.children
  icono.className = `pi ${ids.length > 1 ? 'pi-clone' : item.tipo === 'carpeta' ? 'pi-folder' : 'pi-file'}`
  nombre.textContent = ids.length > 1 ? `${ids.length} elementos` : item.nombre
  cuenta.textContent = ids.length > 1 ? ids.length : ''
  return vistaArrastre.value
}

function handleInicioMover(event, item, index) {
  if (!puedeArrastrar.value) {
    event.preventDefault()
    return
  }
  menuAbierto.value = null
  contextMenu.value.visible = false
  gestor.empezarArrastre(item, index)
  event.dataTransfer.effectAllowed = 'move'
  // Tipo propio: no lleva 'Files', así que no se confunde con subir desde el ordenador
  event.dataTransfer.setData('application/x-pomba-items', gestor.arrastre.ids.join(','))
  event.dataTransfer.setDragImage(prepararVistaArrastre(item), -12, -12)
}

// Filas, migas y "Mi unidad" se marcan con data-carpeta-id ("raiz" es Mi unidad)
function analizarDestino(target) {
  const elemento = target.nodeType === Node.ELEMENT_NODE ? target : target.parentElement
  const carpeta = elemento?.closest('[data-carpeta-id]')
  if (!carpeta) return { destino: null, motivo: null }
  const { carpetaId, carpetaNombre: nombre } = carpeta.dataset
  const id = carpetaId === 'raiz' ? null : Number(carpetaId)
  if (gestor.arrastre.ids.includes(id)) {
    return { destino: null, motivo: 'Una carpeta no puede ir dentro de sí misma' }
  }
  if (id === gestor.carpetaAbiertaId) return { destino: null, motivo: 'Ya está en esta carpeta' }
  return { destino: { id, nombre }, motivo: null }
}

function handleMoverSobre(event) {
  if (!gestor.arrastre.ids.length) return
  const { destino, motivo } = analizarDestino(event.target)
  gestor.marcarDestinoArrastre(destino, motivo)
  if (!destino) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
}

function handleSoltarMover(event) {
  const { ids } = gestor.arrastre
  if (!ids.length) return
  const { destino } = analizarDestino(event.target)
  gestor.limpiarArrastre()
  if (!destino) return
  event.preventDefault()
  gestor.moverItems(ids, destino.id)
}

async function accionContextMenu(accion) {
  contextMenu.value.visible = false
  const ids = gestor.seleccion.ids

  if (accion === 'nuevaCarpeta') {
    gestor.abrirModal('crearCarpeta')
  } else if (accion === 'subirArchivo' || accion === 'subirCarpeta') {
    gestor.elegirYSubir(accion === 'subirCarpeta' ? 'carpeta' : 'archivo', carpetaActual())
  } else if (accion === 'info') {
    const item = gestor.itemsSeleccionados[0]
    if (item) gestor.abrirPanelInfo(item)
  } else if (accion === 'preview') {
    const item = gestor.itemsSeleccionados[0]
    if (item) await gestor.abrirModalPrevisualizar(item)
  } else if (accion === 'download') {
    await gestor.descargarItems()
  } else if (accion === 'favorite' || accion === 'unfavorite') {
    await gestor.marcarFavoritos(ids)
  } else if (accion === 'delete') {
    await gestor.eliminarItems(ids)
  } else if (accion === 'restore') {
    await gestor.restaurarItems(ids)
  } else if (accion === 'deleteForever') {
    const ok = await confirmar({
      header: '¿Eliminar definitivamente?',
      mensaje: 'Esta acción no se puede deshacer.',
      labelAceptar: 'Eliminar',
      peligro: true,
    })
    if (ok) await gestor.eliminarDefinitivamente(ids)
  } else {
    emit(accion)
  }
}

// === Cierre de menús ===========================================
function handleDocumentClick() {
  if (menuAbierto.value !== null) menuAbierto.value = null
  if (contextMenu.value.visible) contextMenu.value.visible = false
}

// La tecla "delete" del Mac envía Backspace; en Windows y Linux Backspace no borra
const esMac = /Mac/i.test(navigator.platform)

function handleTeclaEliminar(event) {
  const conModificador = event.ctrlKey || event.metaKey || event.altKey || event.shiftKey
  const escribiendo = event.target.closest?.('input, textarea, select, [contenteditable="true"]')
  const ventanaAbierta = document.querySelector('.p-dialog')
  if (esTactil || event.repeat || conModificador || escribiendo || ventanaAbierta) return
  if (!gestor.seleccion.ids.length || gestor.arrastre.ids.length) return
  event.preventDefault()
  menuAbierto.value = null
  accionContextMenu(enPapelera.value ? 'deleteForever' : 'delete')
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    menuAbierto.value = null
    contextMenu.value.visible = false
  } else if (event.key === 'Delete' || (esMac && event.key === 'Backspace')) {
    handleTeclaEliminar(event)
  }
}

document.addEventListener('click', handleDocumentClick)
document.addEventListener('keydown', handleKeydown)
document.addEventListener('dragover', handleMoverSobre)
document.addEventListener('drop', handleSoltarMover)
document.addEventListener('dragend', gestor.limpiarArrastre)
onUnmounted(() => {
  document.removeEventListener('click', handleDocumentClick)
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('dragover', handleMoverSobre)
  document.removeEventListener('drop', handleSoltarMover)
  document.removeEventListener('dragend', gestor.limpiarArrastre)
  clearTimeout(apagarArrastre)
})

function estaSeleccionado(item) {
  return gestor.seleccion.ids.includes(item.id)
}


const emptyState = computed(() => {
  const estados = {
    drive:  { icon: 'pi-cloud-upload', titulo: 'Tu unidad está vacía',    desc: 'Sube tu primer archivo o crea una carpeta con el botón Nuevo' },
    fav:    { icon: 'pi-star',         titulo: 'Sin favoritos todavía',    desc: 'Marca elementos con ★ para encontrarlos aquí rápidamente' },
    recent: { icon: 'pi-clock',        titulo: 'Sin actividad reciente',   desc: 'Los archivos que subas o abras aparecerán aquí' },
    trash:  { icon: 'pi-trash',        titulo: 'La papelera está vacía',   desc: '' },
  }
  return estados[route.params.view] ?? estados.drive
})

</script>

<template>
  <div
    class="w-full min-h-[max(24rem,100%)] select-none relative"
    @click="handleBackgroundClick"
    @contextmenu="handleContextMenuVacio"
    @dragover="handleDragOver"
    @dragleave="handleDragLeave"
    @drop="handleDrop"
  >

    <!-- Loading  -->
    <div v-if="gestor.loading" class="flex items-center justify-center py-16 text-surface-400">
      <i class="pi pi-spin pi-spinner text-2xl" />
    </div>

    <!-- Vacío -->
    <div
      v-else-if="!gestor.items.length"
      class="flex flex-col items-center justify-center py-24 gap-4"
    >
      <div class="w-16 h-16 rounded-2xl bg-surface-100 dark:bg-surface-800 flex items-center justify-center">
        <i :class="['pi', emptyState.icon, 'text-2xl text-surface-400 dark:text-surface-500']" />
      </div>
      <div class="text-center">
        <p class="text-sm font-semibold text-surface-700 dark:text-surface-300">{{ emptyState.titulo }}</p>
        <p v-if="emptyState.desc" class="text-xs text-surface-400 dark:text-surface-500 mt-1 max-w-60 leading-relaxed">
          {{ emptyState.desc }}
        </p>
      </div>
    </div>

    <!--  Tabla  -->
    <table v-else role="grid" aria-label="Archivos" class="w-full table-fixed border-collapse">
      <thead class="sticky top-0 z-10">
        <tr
          role="presentation"
          class="bg-surface-0 dark:bg-surface-900 border-b border-surface-200 dark:border-surface-800 text-sm font-medium text-surface-400 dark:text-surface-500"
        >
          <th scope="col" class="text-left px-4 py-2 font-medium">
            <button @click="ordenarPor('nombre')" class="flex items-center gap-1 hover:text-surface-600 dark:hover:text-surface-300 transition-colors">
              Nombre
              <i :class="sortCampo === 'nombre' ? (sortDir === 'asc' ? 'pi pi-arrow-up' : 'pi pi-arrow-down') : 'pi pi-arrow-up opacity-0'" class="text-xs" />
            </button>
          </th>
          <th scope="col" class="text-left px-4 py-2 font-medium w-24">
            <button @click="ordenarPor('tamano_bytes')" class="flex items-center gap-1 hover:text-surface-600 dark:hover:text-surface-300 transition-colors">
              Tamaño
              <i :class="sortCampo === 'tamano_bytes' ? (sortDir === 'asc' ? 'pi pi-arrow-up' : 'pi pi-arrow-down') : 'pi pi-arrow-up opacity-0'" class="text-xs" />
            </button>
          </th>
          <th scope="col" class="hidden sm:table-cell text-left px-4 py-2 font-medium w-32">
            <button @click="ordenarPor('fecha_modificacion')" class="flex items-center gap-1 hover:text-surface-600 dark:hover:text-surface-300 transition-colors">
              Modificado
              <i :class="sortCampo === 'fecha_modificacion' ? (sortDir === 'asc' ? 'pi pi-arrow-up' : 'pi pi-arrow-down') : 'pi pi-arrow-up opacity-0'" class="text-xs" />
            </button>
          </th>
          <th scope="col" class="w-10 px-4 py-2" />
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(item, index) in itemsOrdenados"
          :key="item.id"
          role="row"
          :aria-selected="estaSeleccionado(item)"
          :tabindex="index === 0 ? 0 : -1"
          :draggable="puedeArrastrar"
          @dragstart="handleInicioMover($event, item, index)"
          @click.stop="handleClick($event, item, index)"
          @dblclick.stop="handleDoubleClick(item)"
          @contextmenu.stop="handleContextMenu($event, item, index)"
          :data-carpeta-id="item.tipo === 'carpeta' ? item.id : undefined"
          :data-carpeta-nombre="item.tipo === 'carpeta' ? item.nombre : undefined"
          :class="[
            'group cursor-pointer outline-none transition-colors duration-100 border-b border-surface-200 dark:border-surface-800',
            (destinoSoltar?.id === item.id || gestor.esDestinoArrastre(item.id)) && CLASE_DESTINO,
            gestor.arrastre.ids.includes(item.id) && 'opacity-40',
            estaSeleccionado(item)
              ? 'bg-primary/20 dark:bg-primary/25'
              : 'hover:bg-surface-100 dark:hover:bg-surface-800',
          ]"
        >
          <!-- Nombre -->
          <td class="px-4 py-3 max-w-0">
            <div class="flex items-center gap-2 min-w-0">
              <i
                :class="[
                  'pi text-base shrink-0',
                  obtenerIcono(item),
                ]"
              />
              <span class="truncate text-sm">{{ item.nombre }}</span>
              <i v-if="item.favorito" class="pi pi-star-fill text-yellow-400 text-xs shrink-0" />
            </div>
          </td>

          <!-- Tamaño -->
          <td class="px-4 py-3">
            <span class="text-xs text-surface-500 dark:text-surface-400">
              {{ item.tipo === 'carpeta' ? '—' : formatBytes(item.tamano_bytes) }}
            </span>
          </td>

          <!-- Modificado -->
          <td class="hidden sm:table-cell px-4 py-3">
            <span class="text-xs text-surface-500 dark:text-surface-400">
              {{ formatDate(item.fecha_modificacion) }}
            </span>
          </td>

          <!-- Botón ··· -->
          <td class="px-4 py-3">
            <div class="relative flex items-center justify-center">
              <button
                @click.stop="toggleMenu($event, item.id)"
                :aria-label="`Opciones de ${item.nombre}`"
                :class="[
                  'w-7 h-7 shrink-0 flex items-center justify-center rounded-full transition-colors',
                  menuAbierto === item.id
                    ? 'bg-surface-200 dark:bg-surface-700'
                    : 'sm:opacity-0 sm:group-hover:opacity-100 hover:bg-surface-200 dark:hover:bg-surface-700',
                ]"
              >
                <i class="pi pi-ellipsis-h text-surface-400 dark:text-surface-500" style="font-size:13px" />
              </button>

              <!-- Dropdown menú ··· -->
              <Transition name="menu-drop">
                <div
                  v-if="menuAbierto === item.id"
                  @click.stop
                  class="absolute right-0 top-8 z-50 w-44
                        bg-white dark:bg-surface-900
                        border border-surface-200 dark:border-surface-700
                        rounded-xl shadow-lg py-1 overflow-hidden"
                >
                  <template v-if="enPapelera">
                    <button
                      @click="accionMenu($event, 'info', item)"
                      class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                    >
                      <i class="pi pi-info-circle text-surface-400" /> Ver detalles
                    </button>
                    <div class="my-1 border-t border-surface-200 dark:border-surface-800" />
                    <button
                      @click="accionMenu($event, 'restore', item)"
                      class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                    >
                      <i class="pi pi-replay text-surface-400" /> Restaurar
                    </button>
                    <div class="my-1 border-t border-surface-200 dark:border-surface-800" />
                    <button
                      @click="accionMenu($event, 'deleteForever', item)"
                      class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                    >
                      <i class="pi pi-trash" /> Eliminar definitivo
                    </button>
                  </template>

                  <template v-else>
                    <button
                      @click="accionMenu($event, 'info', item)"
                      class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                    >
                      <i class="pi pi-info-circle text-surface-400" /> Ver detalles
                    </button>
                    <div class="my-1 border-t border-surface-200 dark:border-surface-800" />
                    <button
                      v-if="esPrevisualizableItem(item)"
                      @click="accionMenu($event, 'preview', item)"
                      class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                    >
                      <i class="pi pi-eye text-surface-400" /> Previsualizar
                    </button>
                    <button
                      @click="accionMenu($event, 'download', item)"
                      class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                    >
                      <i class="pi pi-download text-surface-400" /> Descargar
                    </button>
                    <button
                      @click="accionMenu($event, 'rename', item)"
                      class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                    >
                      <i class="pi pi-pencil text-surface-400" /> Cambiar nombre
                    </button>
                    <button
                      v-if="!item.favorito"
                      @click="accionMenu($event, 'favorite', item)"
                      class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                    >
                      <i class="pi pi-star text-surface-400" /> Marcar favorito
                    </button>
                    <button
                      v-else
                      @click="accionMenu($event, 'unfavorite', item)"
                      class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                    >
                      <i class="pi pi-star-fill text-yellow-400" /> Quitar favorito
                    </button>
                    <button
                      @click="accionMenu($event, 'move', item)"
                      class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
                    >
                      <i class="pi pi-arrow-right text-surface-400" /> Mover a...
                    </button>
                    <div class="my-1 border-t border-surface-200 dark:border-surface-800" />
                    <button
                      @click="accionMenu($event, 'delete', item)"
                      class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                    >
                      <i class="pi pi-trash" /> Eliminar
                    </button>
                  </template>
                </div>
              </Transition>
            </div>
          </td>
        </tr>
      </tbody>
    </table>

  </div>

  <!-- Aviso al arrastrar ficheros del ordenador -->
  <Teleport to="body">
    <div
      v-if="arrastrando && marcoSoltar"
      class="fixed z-150 pointer-events-none rounded-b-2xl border-2 border-dashed border-primary bg-primary/5"
      :style="marcoSoltar"
    />
    <div
      v-if="arrastrando"
      class="fixed bottom-10 left-1/2 -translate-x-1/2 z-200 pointer-events-none
             flex items-center gap-2 px-4 py-2.5 rounded-full shadow-lg
             bg-primary text-primary-contrast text-sm font-medium"
    >
      <i class="pi pi-cloud-upload" /> <span>Suelta para subir a <b>{{ nombreDestino }}</b></span>
    </div>
  </Teleport>

  <!-- Mover arrastrando: imagen junto al ratón (fuera de la pantalla) y aviso de abajo -->
  <Teleport to="body">
    <div
      ref="vistaArrastre"
      aria-hidden="true"
      class="fixed -top-[9999px] -left-[9999px] flex items-center gap-2 max-w-72 px-3 py-1.5 rounded-full
             bg-primary text-primary-contrast text-sm font-medium whitespace-nowrap"
    >
      <i /><span class="truncate" /><b class="px-1.5 rounded-full bg-white/25 text-xs empty:hidden" />
    </div>
    <div
      v-if="gestor.arrastre.ids.length"
      role="status"
      :class="[
        'fixed bottom-10 left-1/2 -translate-x-1/2 z-200 pointer-events-none max-w-[90vw]',
        'flex items-center gap-2 px-4 py-2.5 rounded-full shadow-lg text-sm font-medium whitespace-nowrap',
        gestor.arrastre.destino
          ? 'bg-primary text-primary-contrast'
          : ['bg-surface-800 dark:bg-surface-700', gestor.arrastre.motivo ? 'text-red-200' : 'text-surface-0'],
      ]"
    >
      <template v-if="gestor.arrastre.destino">
        <i class="pi pi-arrow-right" />
        <span class="truncate">Mover {{ queSeMueve }} a <b>{{ gestor.arrastre.destino.nombre }}</b></span>
      </template>
      <template v-else-if="gestor.arrastre.motivo">
        <i class="pi pi-ban" /> <span>{{ gestor.arrastre.motivo }}</span>
      </template>
      <template v-else>
        <i class="pi pi-arrows-alt" /> <span>Arrastra hasta una carpeta</span>
      </template>
    </div>
  </Teleport>

  <!-- Context menu (click derecho) -->
  <Teleport to="body">
    <Transition name="menu-drop">
      <div
        v-if="contextMenu.visible"
        @click.stop
        class="fixed z-200 w-44
              bg-white dark:bg-surface-900
              border border-surface-200 dark:border-surface-700
              rounded-xl shadow-lg py-1 overflow-hidden"
        :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
      >
        <template v-if="contextMenu.vacio">
          <button
            @click="accionContextMenu('nuevaCarpeta')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
          >
            <i class="pi pi-folder text-surface-400" /> Nueva carpeta
          </button>
          <div class="my-1 border-t border-surface-200 dark:border-surface-800" />
          <button
            @click="accionContextMenu('subirArchivo')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
          >
            <i class="pi pi-upload text-surface-400" /> Subir archivo
          </button>
          <button
            @click="accionContextMenu('subirCarpeta')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
          >
            <i class="pi pi-folder-open text-surface-400" /> Subir carpeta
          </button>
        </template>

        <template v-else-if="enPapelera">
          <button
            @click="accionContextMenu('info')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
          >
            <i class="pi pi-info-circle text-surface-400" /> Ver detalles
          </button>
          <div class="my-1 border-t border-surface-200 dark:border-surface-800" />
          <button
            @click="accionContextMenu('restore')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
          >
            <i class="pi pi-replay text-surface-400" /> Restaurar
          </button>
          <div class="my-1 border-t border-surface-200 dark:border-surface-800" />
          <button
            @click="accionContextMenu('deleteForever')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
          >
            <i class="pi pi-trash" /> Eliminar definitivo
          </button>
        </template>

        <template v-else>
          <button
            v-if="gestor.seleccion.ids.length === 1"
            @click="accionContextMenu('info')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
          >
            <i class="pi pi-info-circle text-surface-400" /> Ver detalles
          </button>
          <div v-if="gestor.seleccion.ids.length === 1" class="my-1 border-t border-surface-200 dark:border-surface-800" />
          <button
            v-if="gestor.seleccion.ids.length === 1 && esPrevisualizableItem(contextMenu.item)"
            @click="accionContextMenu('preview')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
          >
            <i class="pi pi-eye text-surface-400" /> Previsualizar
          </button>
          <button
            @click="accionContextMenu('download')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
          >
            <i class="pi pi-download text-surface-400" /> Descargar
          </button>
          <button
            v-if="gestor.seleccion.ids.length === 1"
            @click="accionContextMenu('rename')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
          >
            <i class="pi pi-pencil text-surface-400" /> Cambiar nombre
          </button>
          <button
            v-if="gestor.seleccion.ids.length === 1 && !gestor.itemsSeleccionados[0]?.favorito"
            @click="accionContextMenu('favorite')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
          >
            <i class="pi pi-star text-surface-400" /> Marcar favorito
          </button>
          <button
            v-else-if="gestor.seleccion.ids.length === 1 && gestor.itemsSeleccionados[0]?.favorito"
            @click="accionContextMenu('unfavorite')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
          >
            <i class="pi pi-star-fill text-yellow-400" /> Quitar favorito
          </button>
          <button
            @click="accionContextMenu('move')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-surface-700 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
          >
            <i class="pi pi-arrow-right text-surface-400" /> Mover a...
          </button>
          <div class="my-1 border-t border-surface-200 dark:border-surface-800" />
          <button
            @click="accionContextMenu('delete')"
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-left text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
          >
            <i class="pi pi-trash" /> Eliminar
          </button>
        </template>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.menu-drop-enter-active,
.menu-drop-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.menu-drop-enter-from { opacity: 0; transform: translateY(-6px) scale(0.97); }
.menu-drop-leave-to   { opacity: 0; transform: translateY(-6px) scale(0.97); }
</style>
