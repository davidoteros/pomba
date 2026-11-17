<script setup>
import { ref, computed } from 'vue'

import { useRoute, useRouter } from 'vue-router'
import { useGestorItems } from '@/stores/items'
import { useUserStore } from '@/stores/user'
import { useConfirmacion } from '@/composables/useConfirmacion'
import EspacioUsado from '@/components/EspacioUsado.vue'

import ContextMenu from 'primevue/contextmenu'
import Menu from 'primevue/menu'

// Utilizamos PERFIL para mostrar el avatar de usuario en la barra de navegación móvil
// AppLayout es el encargado de pasarlo y es el dueño del dato.
const emit = defineEmits(['abrir-ajustes'])

const route = useRoute()
const router = useRouter()
const gestor = useGestorItems()
const userStore = useUserStore()
const { confirmar } = useConfirmacion()

const menuPapelera = ref(null)
const nuevoMenu = ref(null)

// Este es el menú de acción para las pantallas táctiles (Subir archivo, subir carpeta o crear carpeta) - Con el controlamos que aparezca o no
const fabAbierto = ref(false)

const nuevoMenuItems = [
  {
    label: 'Nueva carpeta',
    icon: 'pi pi-folder',
    command: () => { gestor.abrirModal('crearCarpeta'); fabAbierto.value = false },
  },
  { separator: true },
  {
    label: 'Subir archivo',
    icon: 'pi pi-upload',
    command: () => { gestor.elegirYSubir('archivo', carpetaActual()); fabAbierto.value = false },
  },
  {
    label: 'Subir carpeta',
    icon: 'pi pi-folder-open',
    command: () => { gestor.elegirYSubir('carpeta', carpetaActual()); fabAbierto.value = false },
  },
]

const trashMenuItems = [
  {
    label: 'Vaciar papelera',
    icon: 'pi pi-trash',
    command: async () => {
      const ok = await confirmar({
        header: '¿Vaciar la papelera?',
        mensaje: 'Se eliminarán todos los archivos permanentemente.',
        labelAceptar: 'Vaciar',
        peligro: true,
      })
      if (ok) await gestor.vaciarPapelera()
    },
  },
  {
    label: 'Restaurar todo',
    icon: 'pi pi-replay',
    command: async () => await gestor.restaurarPapelera(),
  },
]

// === Navegación ======================================================
const active = computed(() => route.params.view || 'drive')

const navItems = [
  { key: 'drive',  label: 'Mi unidad', icon: 'pi pi-folder' },
  { key: 'fav',    label: 'Favoritos', icon: 'pi pi-star' },
  { key: 'recent', label: 'Reciente',  icon: 'pi pi-clock' },
  { key: 'trash',  label: 'Papelera',  icon: 'pi pi-trash' },
]

function setActive(key) {
  router.push({ name: 'home', params: { view: key } })
}

function toggleMenuPapelera(event) {
  menuPapelera.value.show(event)
}

function toggleNuevoMenu(event) {
  nuevoMenu.value.toggle(event)
}

function handleFAB(event) {
  if (window.innerWidth >= 640) {
    toggleNuevoMenu(event)
  } else {
    fabAbierto.value = !fabAbierto.value
  }
}

function cerrarFAB() { fabAbierto.value = false }

// Lo que se suba va a la carpeta abierta (o a la raíz)
function carpetaActual() {
  return route.params.folderId ? Number(route.params.folderId) : null
}


function togglePanelUsuario() {
  emit('abrir-ajustes')
}
</script>

<template>
  <!--  SIDEBAR DESKTOP -->
  <aside class="hidden sm:flex w-full h-full flex-col sm:items-center sm:p-1 lg:items-stretch lg:p-3">

    <!-- Botón Nuevo -->
    <button
      @click="toggleNuevoMenu"
      class="mb-4 flex items-center justify-center gap-2 bg-primary text-primary-contrast rounded-full text-base font-medium
            hover:bg-primary/90 active:scale-[0.98] transition-all duration-150 shadow-sm
            sm:w-10 sm:h-10 sm:p-0
            lg:w-full lg:h-auto lg:px-4 lg:py-2.5"
      title="Nuevo"
    >
      <i class="pi pi-plus text-sm" />
      <span class="hidden lg:inline">Nuevo</span>
    </button>

    <Menu ref="nuevoMenu" :model="nuevoMenuItems" popup :pt="{
      itemLabel: { class: 'text-s' },
      itemIcon:  { class: 'text-s' },
    }" />
    <ContextMenu ref="menuPapelera" :model="trashMenuItems" />

    <!-- Navegación -->
    <nav class="flex flex-col gap-1 w-full">
      <button
        v-for="item in navItems"
        :key="item.key"
        @click="setActive(item.key)"
        @contextmenu.prevent="item.key === 'trash' && toggleMenuPapelera($event)"
        :title="item.label"
        :class="[
          'flex items-center py-2 rounded-lg transition-all duration-200 cursor-pointer border-none outline-none text-sm w-full',
          'sm:justify-center sm:px-2 sm:gap-0 lg:justify-start lg:px-3 lg:gap-5 lg:text-left',
          active === item.key
            ? 'bg-primary text-primary-contrast shadow-sm'
            : 'text-surface-700 dark:text-surface-200 hover:bg-surface-200 dark:hover:bg-surface-800',
        ]"
      >
        <i :class="[item.icon, 'text-base']" />
        <span class="hidden lg:inline font-medium">{{ item.label }}</span>
      </button>
    </nav>

    <EspacioUsado variante="lateral" class="mt-auto" />

  </aside>

  <!-- BOTTOM NAV MÓVIL  -->
  <Teleport to="body">
    <nav
      class="sm:hidden fixed bottom-0 left-0 right-0 z-40
            bg-surface-0/95 dark:bg-surface-900/95
            backdrop-blur-md
            border-t border-surface-200 dark:border-surface-700
            flex items-stretch"
      style="padding-bottom: env(safe-area-inset-bottom);"
    >
      <button
        v-for="item in navItems"
        :key="item.key"
        @click="setActive(item.key)"
        :class="[
          'flex-1 flex flex-col items-center justify-center gap-1 py-2.5 transition-colors',
          active === item.key ? 'text-primary' : 'text-surface-500 dark:text-surface-400',
        ]"
        :aria-label="item.label"
        :aria-current="active === item.key ? 'page' : undefined"
      >
        <i :class="[item.icon, 'text-xl']" />
        <span :class="['text-[10px] font-medium leading-none', active === item.key ? 'text-primary' : 'text-surface-400 dark:text-surface-500']">
          {{ item.label }}
        </span>
      </button>

      <!-- Avatar/usuario -->
      <button
        @click="togglePanelUsuario"
        class="flex-1 flex flex-col items-center justify-center gap-1 py-2.5 text-surface-500 dark:text-surface-400 transition-colors"
        aria-label="Mi cuenta"
      >
        <div class="w-6 h-6 rounded-full overflow-hidden bg-surface-200 dark:bg-surface-700 flex items-center justify-center ring-2 ring-transparent transition-all">
          <img v-if="userStore.perfil.foto_perfil_url" :src="userStore.perfil.foto_perfil_url" class="w-full h-full object-cover" />
          <span v-else-if="userStore.inicial" class="text-[10px] font-semibold text-surface-600 dark:text-surface-300 leading-none">{{ userStore.inicial }}</span>
          <i v-else class="pi pi-user text-surface-500" style="font-size:11px" />
        </div>
        <span class="text-[10px] font-medium leading-none text-surface-400 dark:text-surface-500">Cuenta</span>
      </button>
    </nav>
  </Teleport>

  <!-- FAB MÓVIL (botón +)  -->
  <Teleport to="body">
    <!-- Overlay para cerrar el mini-menú -->
    <Transition name="fab-overlay">
      <div
        v-if="fabAbierto"
        class="sm:hidden fixed inset-0 z-45"
        @click="cerrarFAB"
      />
    </Transition>

    <!-- Minimenú del FAB -->
    <Transition name="fab-menu">
      <div
        v-if="fabAbierto"
        class="sm:hidden fixed z-46 flex flex-col gap-2"
        style="bottom: calc(4.5rem + env(safe-area-inset-bottom) + 4.5rem); right: 1.25rem;"
      >
        <button
          v-for="opcion in nuevoMenuItems.filter(o => !o.separator)"
          :key="opcion.label"
          @click="opcion.command"
          class="flex items-center gap-3 bg-surface-0 dark:bg-surface-800
                border border-surface-200 dark:border-surface-700
                rounded-2xl px-4 py-3 shadow-lg text-sm font-medium
                text-surface-700 dark:text-surface-200
                active:scale-95 transition-transform"
        >
          <div class="w-8 h-8 rounded-xl bg-primary/10 dark:bg-primary/20 flex items-center justify-center">
            <i :class="[opcion.icon, 'text-primary text-sm']" />
          </div>
          {{ opcion.label }}
        </button>
      </div>
    </Transition>

    <!-- Botón FAB -->
    <button
      class="sm:hidden fixed z-47 w-14 h-14 rounded-full bg-primary shadow-lg
            flex items-center justify-center
            active:scale-95 transition-all duration-200"
      style="bottom: calc(env(safe-area-inset-bottom) + 4.5rem); right: 1.25rem;"
      :class="fabAbierto ? 'rotate-45' : 'rotate-0'"
      @click="handleFAB"
      aria-label="Nueva acción"
    >
      <i class="pi pi-plus text-primary-contrast text-xl transition-transform duration-200" />
    </button>
  </Teleport>
</template>

<style scoped>
.fab-overlay-enter-active,
.fab-overlay-leave-active {
  transition: opacity 0.2s ease;
}
.fab-overlay-enter-from,
.fab-overlay-leave-to {
  opacity: 0;
}

.fab-menu-enter-active {
  transition: opacity 0.2s ease, transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.fab-menu-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.fab-menu-enter-from,
.fab-menu-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.95);
}
</style>
