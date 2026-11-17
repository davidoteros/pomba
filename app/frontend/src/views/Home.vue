<script setup>
import { ref, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useGestorItems } from '@/stores/items'
import { useConfirmacion } from '@/composables/useConfirmacion'

import FileTable from '../components/FileTable.vue'
import Popover from 'primevue/popover'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Divider from 'primevue/divider'


const gestor = useGestorItems()
const route = useRoute()
const router = useRouter()
const { confirmar } = useConfirmacion()

const inputNuevaCarpeta = ref('')
const errorNuevaCarpeta = ref('')
const popoverBreadcrumb = ref()

function togglePopoverBreadcrumb(event) {
  popoverBreadcrumb.value?.toggle(event)
}

function navegarDesdePopover(item) {
  item.command()
  popoverBreadcrumb.value?.hide()
}

const CONFIGURACION_VISTAS = {
  drive: {
    titulo: 'Mi unidad',
    icono: 'pi pi-folder',
    paramsBase: { papelera: 'false', favoritos: 'false' },
  },
  trash: {
    titulo: 'Papelera',
    icono: 'pi pi-trash',
    paramsBase: { papelera: 'true' },
  },
  fav: {
    titulo: 'Favoritos',
    icono: 'pi pi-star',
    paramsBase: { papelera: 'false', favorito: 'true' },
  },
  recent: {
    titulo: 'Recientes',
    icono: 'pi pi-clock',
    paramsBase: { recientes: 'true' },
  },
}

const enPapelera = computed(() => (route.params.view || 'drive') === 'trash')

const breadcrumbInicio = computed(() => {
  const vistaActual = route.params.view || 'drive'
  const config = CONFIGURACION_VISTAS[vistaActual]
  return {
    label: config?.titulo || 'Mi unidad',
    icon: config?.icono || 'pi pi-home',
    command: () => router.push({ name: 'home', params: { view: vistaActual } }),
  }
})

const rutaBreadcrumb = computed(() =>
  gestor.breadcrumb
    .filter((nodo) => nodo.id !== null)
    .map((nodo) => ({
      label: nodo.label,
      id: nodo.id,
      command: () =>
        router.push({
          name: 'home',
          params: { view: route.params.view || 'drive', folderId: nodo.id },
        }),
    }))
)

function cargarDesdeRuta() {
  const vista = route.params.view || 'drive'
  const folderId = route.params.folderId || null
  const config = CONFIGURACION_VISTAS[vista] || CONFIGURACION_VISTAS.drive
  return gestor.cargarItems({ ...config.paramsBase, carpeta: folderId })
}

function cerrarModal() {
  gestor.cerrarModal()
  inputNuevaCarpeta.value = ''
  errorNuevaCarpeta.value = ''
}

async function crearCarpeta() {
  const idPadre = route.params.folderId || null
  errorNuevaCarpeta.value = await gestor.crearCarpeta({ nombre: inputNuevaCarpeta.value, tipo: 'carpeta', padre: idPadre }) || ''
  if (!errorNuevaCarpeta.value) {
    cerrarModal()
    await cargarDesdeRuta()
  }
}

// === Barra de acciones para elementos seleccionados ==================
async function eliminar() {
  const ids = gestor.itemsSeleccionados.map((i) => i.id)
  if (!ids.length) return
  await gestor.eliminarItems(ids)
}

async function eliminarDefinitivamente() {
  const ids = gestor.itemsSeleccionados.map((i) => i.id)
  if (!ids.length) return
  const ok = await confirmar({
    header: '¿Eliminar definitivamente?',
    mensaje: 'Esta acción no se puede deshacer.',
    labelAceptar: 'Eliminar',
    peligro: true,
  })
  if (ok) await gestor.eliminarDefinitivamente(ids)
}

async function restaurar() {
  const ids = gestor.itemsSeleccionados.map((i) => i.id)
  if (!ids.length) return
  await gestor.restaurarItems(ids)
}

async function descargar() {
  await gestor.descargarItems()
}

watch(
  () => [route.params.view, route.params.folderId],
  async () => {
    gestor.limpiarSeleccion()
    popoverBreadcrumb.value?.hide()
    await cargarDesdeRuta()
  },
  { immediate: true }
)
</script>

<template>
  <div class="flex flex-col h-full">

    <!-- ZONA FIJA: breadcrumb + action bar -->
    <div class="px-4 pt-4 space-y-4 shrink-0">

    <!-- BREADCRUMB -->
    <nav class="flex items-center flex-nowrap gap-0.5">

      <!-- SIN COLAPSO: raíz + hasta 2 sub-niveles -->
      <template v-if="rutaBreadcrumb.length <= 2">
        <span
          v-if="rutaBreadcrumb.length === 0"
          class="flex items-center gap-2 px-2 py-1 text-lg font-bold
                 text-surface-900 dark:text-surface-0"
        >
          <i :class="[breadcrumbInicio.icon, 'text-lg']" />
          {{ breadcrumbInicio.label }}
        </span>
        <!-- Con subcarpetas: raíz clicable + ítems -->
        <template v-else>
          <button
            @click="breadcrumbInicio.command()"
            class="flex items-center gap-1.5 px-2 py-1 rounded-md text-base font-medium shrink-0
                   text-surface-500 dark:text-surface-400
                   hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors cursor-pointer"
          >
            <i :class="[breadcrumbInicio.icon, 'text-xs']" />
            <span>{{ breadcrumbInicio.label }}</span>
          </button>
          <template v-for="(item, idx) in rutaBreadcrumb" :key="item.id">
            <i class="pi pi-angle-right text-sm text-surface-300 dark:text-surface-600 shrink-0 mx-0.5" />
            <button
              v-if="idx < rutaBreadcrumb.length - 1"
              @click="item.command()"
              class="max-w-36 truncate px-2 py-1 rounded-md text-base font-medium shrink-0
                     text-surface-500 dark:text-surface-400
                     hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors cursor-pointer"
            >{{ item.label }}</button>
            <span
              v-else
              class="max-w-56 truncate px-2 py-1 text-lg font-bold text-surface-900 dark:text-surface-0 shrink-0"
            >{{ item.label }}</span>
          </template>
        </template>
      </template>

      <!-- COLAPSADO: ··· > padre > actual -->
      <template v-else>
        <button
          @click="togglePopoverBreadcrumb($event)"
          title="Mostrar ruta completa"
          class="px-2 py-0.5 rounded text-base font-bold tracking-widest shrink-0
                text-surface-400 dark:text-surface-500
                hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors cursor-pointer"
        >···</button>

        <i class="pi pi-angle-right text-sm text-surface-300 dark:text-surface-600 shrink-0 mx-0.5" />
        <!-- Padre del actual -->
        <button
          @click="rutaBreadcrumb.at(-2).command()"
          class="max-w-36 truncate px-2 py-1 rounded-md text-base font-medium shrink-0
                text-surface-500 dark:text-surface-400
                hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors cursor-pointer"
        >{{ rutaBreadcrumb.at(-2).label }}</button>

        <i class="pi pi-angle-right text-sm text-surface-300 dark:text-surface-600 shrink-0 mx-0.5" />
        <!-- Actual — título de página, no clicable -->
        <span class="max-w-56 truncate px-2 py-1 text-lg font-bold text-surface-900 dark:text-surface-0 shrink-0">
          {{ rutaBreadcrumb.at(-1).label }}
        </span>
      </template>

    </nav>

    <!-- Popover -->
    <Popover ref="popoverBreadcrumb">
      <div class="flex flex-col gap-0.5 min-w-44 py-1">
        <p class="px-3 pt-1 pb-2 text-xs font-semibold uppercase tracking-wider
                  text-surface-400 dark:text-surface-500">Ruta completa</p>
        <button
          @click="navegarDesdePopover(breadcrumbInicio)"
          class="flex items-center gap-2 px-3 py-2 rounded-md text-sm text-left w-full
                text-surface-700 dark:text-surface-200
                hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors cursor-pointer"
        >
          <i :class="[breadcrumbInicio.icon, 'text-xs text-surface-400 dark:text-surface-500 shrink-0']" />
          <span class="truncate">{{ breadcrumbInicio.label }}</span>
        </button>
        <button
          v-for="item in rutaBreadcrumb.slice(0, -2)"
          :key="item.id"
          @click="navegarDesdePopover(item)"
          class="flex items-center gap-2 px-3 py-2 rounded-md text-sm text-left w-full
                text-surface-700 dark:text-surface-200
                hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors cursor-pointer"
        >
          <i class="pi pi-folder text-xs text-surface-400 dark:text-surface-500 shrink-0" />
          <span class="truncate">{{ item.label }}</span>
        </button>
      </div>
    </Popover>

    <!-- ACTION BAR — solo en desktop (sm:flex).
      En móvil las acciones vienen del menú ··· y de la barra de selección integrada en FileTable. -->
    <div class="h-9 hidden sm:block">
      <Transition
        enter-active-class="transition-all duration-150 ease-out"
        enter-from-class="opacity-0 -translate-y-1"
        leave-active-class="transition-all duration-150 ease-in"
        leave-to-class="opacity-0 -translate-y-1"
      >
        <div
          v-if="gestor.itemsSeleccionados.length > 0"
          class="flex items-center gap-1
                bg-surface-0 dark:bg-surface-900
                border border-surface-200 dark:border-surface-700
                rounded-full px-2 py-1 h-9 w-fit"
        >
          <div class="flex items-center gap-2 pr-3 border-r border-surface-200 dark:border-surface-700 mr-1">
            <button
              @click="gestor.limpiarSeleccion()"
              aria-label="Deseleccionar todo"
              class="w-6 h-6 rounded-full flex items-center justify-center
                    text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800
                    transition-colors cursor-pointer"
            >
              <i class="pi pi-times text-xs" />
            </button>
            <span class="text-xs font-medium whitespace-nowrap">
              {{ gestor.itemsSeleccionados.length }}
              {{ gestor.itemsSeleccionados.length === 1 ? 'seleccionado' : 'seleccionados' }}
            </span>
          </div>

          <template v-if="enPapelera">
            <Button icon="pi pi-replay" label="Restaurar" text size="small" rounded @click="restaurar" />
            <Divider layout="vertical" class="h-4! mx-1!" />
            <Button icon="pi pi-trash" label="Eliminar definitivo" text size="small" rounded severity="danger" @click="eliminarDefinitivamente" />
          </template>

          <template v-else>
            <Button icon="pi pi-download" label="Descargar" text size="small" rounded :loading="gestor.descargando" @click="descargar()" />
            <Button icon="pi pi-arrow-right" label="Mover" text size="small" rounded @click="gestor.abrirModalMover()" />
            <Button v-if="gestor.itemsSeleccionados.length === 1" icon="pi pi-pencil" label="Renombrar" text size="small" rounded @click="gestor.abrirModalRenombrar()" />
            <Divider layout="vertical" class="h-4! mx-1!" />
            <Button icon="pi pi-trash" label="Eliminar" text size="small" rounded severity="danger" @click="eliminar" />
          </template>
        </div>
      </Transition>
    </div>
    </div>

    <!-- ZONA SCROLLABLE: tabla de archivos -->
    <div class="flex-1 min-h-0 overflow-auto pb-24 lg:pb-0
                [&::-webkit-scrollbar]:w-1.5
                [&::-webkit-scrollbar-track]:bg-transparent
                [&::-webkit-scrollbar-thumb]:rounded-full
                [&::-webkit-scrollbar-thumb]:bg-surface-300
                dark:[&::-webkit-scrollbar-thumb]:bg-surface-600">
      <FileTable @rename="gestor.abrirModalRenombrar" @move="gestor.abrirModalMover" />
    </div>

    <!-- MODAL NUEVA CARPETA -->
    <Dialog
      v-if="gestor.modal.name === 'crearCarpeta'"
      v-model:visible="gestor.modal.open"
      header="Nueva Carpeta"
      :style="{ width: '25rem' }"
      modal :draggable="false" :closable="false"
    >
      <div class="flex flex-col gap-2 mb-4">
        <InputText
          id="folderName"
          v-model="inputNuevaCarpeta"
          class="flex-auto"
          autocomplete="off"
          placeholder="Nombre de la carpeta"
          maxlength="255"
          :invalid="!!errorNuevaCarpeta"
          @input="errorNuevaCarpeta = ''"
          @keyup.enter="crearCarpeta"
          autofocus
        />
        <Message v-if="errorNuevaCarpeta" severity="error" size="small" variant="simple">{{ errorNuevaCarpeta }}</Message>
      </div>
      <template #footer>
        <Button label="Cancelar" text severity="secondary" @click="cerrarModal" />
        <Button label="Crear" @click="crearCarpeta" :disabled="!inputNuevaCarpeta.trim()" />
      </template>
    </Dialog>

  </div>
</template>

