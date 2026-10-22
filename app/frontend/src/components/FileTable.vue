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
const contextMenu = ref({ visible: false, x: 0, y: 0, item: null })

function handleContextMenu(event, item, index) {
  event.preventDefault()
  menuAbierto.value = null

  if (!gestor.seleccion.ids.includes(item.id)) {
    gestor.seleccionar(item, index)
  }

  const MENU_W = 176
  const MENU_H = 230
  const x = event.clientX + MENU_W > window.innerWidth ? event.clientX - MENU_W : event.clientX
  const y = event.clientY + MENU_H > window.innerHeight ? event.clientY - MENU_H : event.clientY

  contextMenu.value = { visible: true, x, y, item }
}

async function accionContextMenu(accion) {
  contextMenu.value.visible = false
  const ids = gestor.seleccion.ids

  if (accion === 'info') {
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

function handleKeydown(event) {
  if (event.key === 'Escape') {
    menuAbierto.value = null
    contextMenu.value.visible = false
  }
}

document.addEventListener('click', handleDocumentClick)
document.addEventListener('keydown', handleKeydown)
onUnmounted(() => {
  document.removeEventListener('click', handleDocumentClick)
  document.removeEventListener('keydown', handleKeydown)
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
    class="w-full min-h-96 select-none relative"
    @click="handleBackgroundClick"
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
          @click.stop="handleClick($event, item, index)"
          @dblclick.stop="handleDoubleClick(item)"
          @contextmenu="handleContextMenu($event, item, index)"
          :class="[
            'group cursor-pointer transition-colors duration-100 border-b border-surface-200 dark:border-surface-800',
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
        <template v-if="enPapelera">
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
