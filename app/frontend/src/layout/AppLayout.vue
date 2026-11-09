<script setup>
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useGestorItems } from '@/stores/items'
import { useUserStore } from '@/stores/user'
import SettingsModal from '@/components/modals/SettingsModal.vue'
import Sidebar from '@/components/Sidebar.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import ModalRenombrar from '@/components/modals/ModalRenombrar.vue'
import ModalMover from '@/components/modals/ModalMover.vue'
import ModalPrevisualizar from '@/components/modals/ModalPrevisualizar.vue'
import InfoPanel from '@/components/InfoPanel.vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import { useConfirmacion } from '@/composables/useConfirmacion'
import PombaLogo from '@/components/PombaLogo.vue'

const gestor = useGestorItems()
const userStore = useUserStore()
const { estado: confirmacion, aceptar: aceptarConfirmacion, cancelar: cancelarConfirmacion } = useConfirmacion()

const router = useRouter()
const route = useRoute()


// === BUSQUEDA ==============================================
const textoBusqueda = ref('')
let timerBusqueda = null

const mostrarHints = ref(false)

const PREFIJOS_BUSQUEDA = [
  { prefijo: 'artista:', icono: 'pi pi-user',      descripcion: 'Artista' },
  { prefijo: 'album:',   icono: 'pi pi-book',       descripcion: 'Álbum'   },
  { prefijo: 'genero:',  icono: 'pi pi-tag',        descripcion: 'Género'  },
  { prefijo: 'titulo:',  icono: 'pi pi-file-audio', descripcion: 'Título'  },
  { prefijo: 'camara:',  icono: 'pi pi-camera',     descripcion: 'Cámara'  },
  { prefijo: 'año:',     icono: 'pi pi-calendar',   descripcion: 'Año'     },
]

function insertarPrefijo(prefijo) {
  textoBusqueda.value = prefijo
  mostrarHints.value = false
}

function limpiarBusqueda() {
  textoBusqueda.value = ''
}

watch(() => route.query.q, (q) => {
  textoBusqueda.value = q || ''
}, { immediate: true }) //Se ejecuta al montar el componente

watch(textoBusqueda, (valor) => {
  clearTimeout(timerBusqueda)
  const texto = valor.trim()
  if (!texto) {
    if (route.name === 'search') router.push('/home')
    return
  }
  timerBusqueda = setTimeout(() => {
    router.push({ name: 'search', query: { q: texto } })
  }, 400)
})


// === MENU DE USUARIO (ESCRITORIO) =========================
const menuUsuario = ref()
const mostrarAjustes = ref(false)

const opcionesMenu = ref([
  {
    label: 'Configuración',
    icon: 'pi pi-cog',
    command: () => { mostrarAjustes.value = true },
  },
  {
    label: 'API',
    icon: 'pi pi-code',
    command: () => { window.open('/api/schema/swagger/', '_blank') },
  },
  { separator: true },
  {
    label: 'Cerrar sesión',
    icon: 'pi pi-sign-out',
    command: cerrarSesion,
  },
])

function toggleMenuUsuario(evento) {
  menuUsuario.value.toggle(evento)
}

async function cerrarSesion() {
  await userStore.cerrarSesion()
  router.push('/')
}

// === MENU DE USUARIO (MOVIL) ============================
const panelUsuarioMovil = ref(false)


// === SNACKBAR ===========================================
const CLASES_SNACKBAR = {
  neutro:      'bg-surface-800 dark:bg-surface-100 text-white dark:text-surface-900',
  exito:       'bg-green-700 dark:bg-green-100 text-white dark:text-green-900',
  advertencia: 'bg-amber-600 dark:bg-amber-100 text-white dark:text-amber-900',
  peligro:     'bg-red-700 dark:bg-red-100 text-white dark:text-red-900',
}

function clasesSnackbar(notif) {
  if (notif.tipo === 'error') return CLASES_SNACKBAR.peligro
  return CLASES_SNACKBAR[notif.severidad] ?? CLASES_SNACKBAR.neutro
}
</script>

<template>
  <div class="grid grid-cols-1 sm:grid-cols-[60px_1fr] lg:grid-cols-[260px_1fr] grid-rows-[64px_1fr] h-screen w-full bg-surface-100 dark:bg-surface-950 gap-y-2 py-2 pr-3">

    <!-- TOPBAR -->
    <header class="col-span-full grid grid-cols-subgrid items-center z-10">

      <!-- Logo -->
      <div class="hidden sm:flex items-center justify-center gap-3 sm:p-1 lg:py-3 lg:pl-6 lg:justify-start">
        <PombaLogo class="w-11 h-11 shrink-0 text-surface-900 dark:text-surface-0" />
        <span class="hidden lg:block text-2xl font-bold tracking-tight text-surface-900 dark:text-surface-0 select-none">
          Pomba
        </span>
      </div>

      <!-- Buscador + controles -->
      <div class="flex gap-2 items-center pl-4 pr-0 sm:pl-3 lg:pr-6">

        <!-- Buscador -->
        <div class="flex-1">
          <div class="w-full max-w-4xl relative">
            <IconField class="w-full group">
              <InputIcon>
                <i class="pi pi-search text-surface-500 group-focus-within:text-surface-900 dark:group-focus-within:text-surface-0 transition-colors duration-200" />
              </InputIcon>
              <InputText
                v-model="textoBusqueda"
                placeholder="Buscar..."
                class="w-full py-3 px-12 border-none rounded-3xl transition-all duration-200
                      bg-surface-150 dark:bg-surface-800
                      hover:bg-surface-200 dark:hover:bg-surface-700
                      focus:bg-surface-0 dark:focus:bg-surface-900
                      focus:shadow-[0_1px_1px_0_rgba(65,69,73,.3),0_1px_3px_1px_rgba(65,69,73,.15)]
                      dark:focus:shadow-[0_1px_3px_rgba(0,0,0,.5)]"
                @focus="mostrarHints = true"
                @blur="mostrarHints = false"
              />
            </IconField>
            <button
              v-if="textoBusqueda"
              @mousedown.prevent="limpiarBusqueda"
              class="absolute right-3 top-1/2 -translate-y-1/2 z-10
                     w-7 h-7 flex items-center justify-center rounded-full
                     text-surface-500 hover:text-surface-800 dark:hover:text-surface-100
                     hover:bg-surface-200 dark:hover:bg-surface-600
                     transition-colors cursor-pointer"
              aria-label="Limpiar búsqueda"
            >
              <i class="pi pi-times text-xs" />
            </button>

            <!-- Panel de búsqueda avanzada -->
            <Transition
              enter-active-class="transition-all duration-150 ease-out"
              enter-from-class="opacity-0 -translate-y-1"
              leave-active-class="transition-all duration-100 ease-in"
              leave-to-class="opacity-0 -translate-y-1"
            >
              <div
                v-if="mostrarHints && !textoBusqueda"
                class="hidden sm:block absolute top-full left-0 right-0 mt-1 z-50
                      bg-surface-0 dark:bg-surface-900
                      border border-surface-200 dark:border-surface-700
                       rounded-2xl shadow-lg p-3"
              >
                <p class="text-xs font-medium text-surface-400 dark:text-surface-500 mb-2 px-1">
                  Búsqueda por campo
                </p>
                <div class="flex flex-wrap gap-1.5">
                  <button
                    v-for="hint in PREFIJOS_BUSQUEDA"
                    :key="hint.prefijo"
                    @mousedown.prevent="insertarPrefijo(hint.prefijo)"
                    class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-medium
                          bg-surface-100 dark:bg-surface-800
                          text-surface-600 dark:text-surface-300
                          hover:bg-surface-200 dark:hover:bg-surface-700
                          transition-colors cursor-pointer border-0"
                  >
                    <i :class="[hint.icono, 'text-xs']" />
                    {{ hint.descripcion }}
                    <span class="text-surface-400 dark:text-surface-500 font-mono">{{ hint.prefijo }}</span>
                  </button>
                </div>
              </div>
            </Transition>
          </div>
        </div>

        <!-- Controles derecha -->
        <div class="hidden sm:flex items-center gap-2 shrink-0">
          <ThemeToggle />

          <button
            class="w-9 h-9 rounded-full shrink-0 p-0 border-0 bg-transparent focus:outline-none cursor-pointer"
            style="line-height:0"
            @click="toggleMenuUsuario"
            aria-label="Menú de usuario"
          >
            <div class="w-full h-full rounded-full overflow-hidden ring-2 ring-transparent hover:ring-primary transition-all duration-200 bg-surface-200 dark:bg-surface-700 flex items-center justify-center">
              <img
                v-if="userStore.perfil.foto_perfil_url"
                :src="userStore.perfil.foto_perfil_url"
                alt="Avatar"
                class="w-full h-full object-cover block pointer-events-none"
              />
              <span
                v-else-if="userStore.inicial"
                class="text-sm font-semibold text-surface-600 dark:text-surface-300 select-none pointer-events-none leading-none"
              >
                {{ userStore.inicial }}
              </span>
              <i v-else class="pi pi-user text-surface-500 text-sm pointer-events-none" />
            </div>
          </button>

          <Menu ref="menuUsuario" class="text-base" :model="opcionesMenu" popup />
        </div>
      </div>
    </header>

    <!-- SIDEBAR (Desktop) -->
    <aside class="hidden sm:block sm:p-1 lg:p-3">
      <Sidebar @abrir-ajustes="mostrarAjustes = true" />
    </aside>

    <!-- MAIN -->
    <main class="flex min-w-0 overflow-hidden bg-surface-0 dark:bg-surface-900 rounded-2xl ml-3">
      <div class="flex-1 min-w-0 overflow-hidden">
        <router-view />
      </div>
      <InfoPanel />
    </main>

  </div>

  <!-- PANEL USUARIO MÓVIL -->
  <Teleport to="body">
    <Transition name="panel-movil">
      <div
        v-if="panelUsuarioMovil"
        class="lg:hidden fixed inset-0 z-60 flex flex-col justify-end"
      >
        <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="panelUsuarioMovil = false" />
        <div
          class="relative bg-surface-0 dark:bg-surface-900 rounded-t-2xl px-5 pt-5"
          style="padding-bottom: calc(2rem + env(safe-area-inset-bottom))"
        >
          <div class="w-10 h-1 bg-surface-300 dark:bg-surface-600 rounded-full mx-auto mb-5" />

          <div class="flex items-center gap-3 mb-5">
            <div class="w-12 h-12 rounded-full overflow-hidden bg-surface-200 dark:bg-surface-700 flex items-center justify-center shrink-0">
              <img v-if="userStore.perfil.foto_perfil_url" :src="userStore.perfil.foto_perfil_url" class="w-full h-full object-cover" />
              <span v-else-if="userStore.inicial" class="text-lg font-semibold text-surface-600 dark:text-surface-300">{{ userStore.inicial }}</span>
              <i v-else class="pi pi-user text-surface-500" />
            </div>
            <div class="min-w-0">
              <p class="font-semibold text-surface-900 dark:text-surface-0 truncate">{{ userStore.perfil.nombre }} {{ userStore.perfil.apellidos }}</p>
              <p class="text-xs text-surface-500 truncate">{{ userStore.perfil.email }}</p>
            </div>
          </div>

          <div class="flex flex-col gap-1">
            <button
              @click="() => { panelUsuarioMovil = false; mostrarAjustes = true }"
              class="flex items-center gap-3 px-3 py-3 rounded-xl text-sm text-surface-700 dark:text-surface-300 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors text-left w-full"
            >
              <i class="pi pi-cog text-surface-400" /> Configuración
            </button>
            <div class="flex items-center gap-3 px-3 py-3 rounded-xl">
              <i class="pi pi-moon text-surface-400 text-sm" />
              <span class="text-sm text-surface-700 dark:text-surface-300 flex-1">Tema oscuro</span>
              <ThemeToggle />
            </div>
            <div class="my-1 border-t border-surface-100 dark:border-surface-800" />
            <button
              @click="() => { panelUsuarioMovil = false; cerrarSesion() }"
              class="flex items-center gap-3 px-3 py-3 rounded-xl text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors text-left w-full"
            >
              <i class="pi pi-sign-out" /> Cerrar sesión
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <SettingsModal v-model="mostrarAjustes" />

  <!-- SNACKBARS -->
  <div class="fixed bottom-20 left-3 z-50 flex flex-col-reverse gap-2 sm:bottom-6 sm:left-6">
    <TransitionGroup name="snack">
      <div
        v-for="notif in gestor.notificaciones"
        :key="notif.id"
        class="flex items-center gap-3 text-sm font-medium px-4 py-3 rounded-xl shadow-lg"
        :class="clasesSnackbar(notif)"
      >
        <i
          class="pi text-base shrink-0"
          :class="notif.tipo === 'cargando' ? 'pi-spin pi-spinner' : notif.icono"
        />
        <span>{{ notif.mensaje }}</span>
        <button
          v-if="notif.tipo !== 'cargando'"
          @click="gestor.eliminarNotificacion(notif.id)"
          class="ml-1 shrink-0 opacity-60 hover:opacity-100 transition-opacity cursor-pointer"
          aria-label="Cerrar"
        >
          <i class="pi pi-times text-xs" />
        </button>
      </div>
    </TransitionGroup>
  </div>

  <!-- MODALES GLOBALES -->
  <ModalRenombrar />
  <ModalMover />
  <ModalPrevisualizar />

  <!-- DIALOG -->
  <Dialog
    v-model:visible="confirmacion.abierto"
    :header="confirmacion.header"
    modal
    :closable="false"
    :style="{ width: '26rem' }"
    :breakpoints="{ '640px': '90vw' }"
  >
    <p class="text-surface-600 dark:text-surface-300 text-sm">{{ confirmacion.mensaje }}</p>
    <template #footer>
      <Button :label="confirmacion.labelCancelar" text severity="secondary" @click="cancelarConfirmacion" />
      <Button
        :label="confirmacion.labelAceptar"
        :severity="confirmacion.peligro ? 'danger' : undefined"
        @click="aceptarConfirmacion"
      />
    </template>
  </Dialog>
</template>

<style scoped>
.snack-enter-active,
.snack-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.snack-enter-from,
.snack-leave-to { opacity: 0; transform: translateY(0.5rem); }
.snack-move { transition: transform 0.2s ease; }

.panel-movil-enter-active,
.panel-movil-leave-active { transition: opacity 0.25s ease; }
.panel-movil-enter-active .relative,
.panel-movil-leave-active .relative { transition: transform 0.3s cubic-bezier(0.32, 0.72, 0, 1); }
.panel-movil-enter-from,
.panel-movil-leave-to { opacity: 0; }
.panel-movil-enter-from .relative,
.panel-movil-leave-to .relative { transform: translateY(100%); }
</style>
