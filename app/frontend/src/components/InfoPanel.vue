<script setup>
import { computed, watch, ref, onUnmounted } from 'vue'
import { useGestorItems } from '@/stores/items'
import { apiItems } from '@/api/items'
import { useConfirmacion } from '@/composables/useConfirmacion'
import { formatDate } from '@/utils/date'
import { formatBytes } from '@/utils/bytes'
import { obtenerIcono } from '@/utils/iconos'
import { etiquetaAmigable } from '@/utils/metadatos'
import { mensajeDeAccion } from '@/utils/errors'

// === STORE Y COMPOSABLES =============================================
const gestor = useGestorItems()
const { confirmar } = useConfirmacion()

// === PANTALLA RESPONSIVENES ==========================================
//Consultrar el tamaño 
const consultaMediaQuery = typeof window !== 'undefined'
  ? window.matchMedia('(min-width: 1024px)')
  : null

// esGrande = true cuando la pantalla tiene 1024px o más
let pantallaGrandeAhora
if (consultaMediaQuery !== null) {
  pantallaGrandeAhora = consultaMediaQuery.matches  // true o false según el tamaño actual
} else {
  pantallaGrandeAhora = true 
}
const esGrande = ref(pantallaGrandeAhora)

function alCambiarTamano(evento) {
  esGrande.value = evento.matches
}
consultaMediaQuery?.addEventListener('change', alCambiarTamano)
onUnmounted(() => consultaMediaQuery?.removeEventListener('change', alCambiarTamano))

// Extraemos las clases y estilos del panel a computed para no ensuciar el template
const clasePanel = computed(() =>
  esGrande.value
    ? 'shrink-0 overflow-hidden border-l border-surface-200 dark:border-surface-700 bg-surface-0 dark:bg-surface-900'
    : 'fixed right-0 top-0 bottom-0 z-50 w-80 border-l border-surface-200 dark:border-surface-700 shadow-2xl bg-surface-0 dark:bg-surface-900 flex flex-col'
)
const estiloPanel = computed(() =>
  esGrande.value
    ? { width: gestor.panelInfo.visible ? '360px' : '0px', transition: 'width 0.2s ease' }
    : { transform: gestor.panelInfo.visible ? 'translateX(0)' : 'translateX(100%)', transition: 'transform 0.25s cubic-bezier(0.32,0.72,0,1)' }
)

// === ÍTEM SELECCIONADO ===============================
const item = computed(() => gestor.itemPanelInfo)
const tabActiva = ref('detalles')

// Lo decide el servidor: audio y control de versiones encendido en el .env
const mostrarPestanaVersiones = computed(() =>
  item.value?.admite_versiones === true,
)

// Cerrar el panel si el ítem desaparece (borrado o movido fuera de la vista)
watch(item, (nuevoItem) => {
  if (!nuevoItem && gestor.panelInfo.visible) gestor.cerrarPanelInfo()
})

// Cerrar el panel si la selección deja de ser de un solo ítem
watch(
  () => gestor.seleccion.ids,
  (ids) => {
    if (!gestor.panelInfo.visible) return
    if (ids.length !== 1) gestor.cerrarPanelInfo()
  },
  { deep: true },
)

// Volver a Detalles si el ítem ya no es audio (la pestaña Versiones dejaría de tener sentido)
watch(mostrarPestanaVersiones, (disponible) => {
  if (!disponible) tabActiva.value = 'detalles'
})

// === VERSIONES ==================================================
const versiones = ref([])
const numeroActual = ref(1)
const cargandoVersiones = ref(false)
const inputVersion = ref(null)   // referencia al <input type="file"> oculto
const reproduciendo = ref(null)   // 'actual' o número de versión archivada
const urlReproduciendo  = ref('')

async function cargarVersiones() {
  if (!item.value || !mostrarPestanaVersiones.value) return
  cargandoVersiones.value = true
  try {
    const data = await apiItems.listarVersiones(item.value.id)
    versiones.value = data.versiones
    numeroActual.value = data.numero_actual
  } catch (e) {
    gestor.agregarNotificacion({
      id: 'versiones-error', tipo: 'error',
      mensaje: mensajeDeAccion(e, 'No se pudieron cargar las versiones'), icono: 'pi-history',
    })
  } finally {
    cargandoVersiones.value = false
  }
}

function iniciarSubidaVersion() {
  inputVersion.value?.click()
}

async function onArchivoSeleccionado(e) {
  const file = e.target.files[0]
  if (!file) return
  e.target.value = ''
  const ok = await gestor.subirNuevaVersion(file, item.value.id)
  if (ok) await cargarVersiones()
}

async function descargarVersionAntigua(version) {
  try {
    const { url } = await apiItems.descargarVersion(item.value.id, version.numero)
    const a = document.createElement('a')
    a.href = url
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  } catch (e) {
    gestor.agregarNotificacion({
      id: 'descarga-version', tipo: 'error',
      mensaje: mensajeDeAccion(e, 'No se pudo descargar la versión'), icono: 'pi-download',
    })
  }
}

async function marcarComoActual(version) {
  try {
    const itemActualizado = await apiItems.activarVersion(item.value.id, version.numero)
    gestor.actualizarItemsLocal([item.value.id], itemActualizado)
    await cargarVersiones()
  } catch (e) {
    gestor.agregarNotificacion({
      id: 'restaurar-version', tipo: 'error',
      mensaje: mensajeDeAccion(e, 'No se pudo marcar la versión como actual'), icono: 'pi-history',
    })
  }
}

async function eliminarVersion(version) {
  const ok = await confirmar({
    header: `¿Eliminar la versión ${version.numero}?`,
    mensaje: 'El archivo de esta versión se borrará definitivamente de S3. Esta acción no se puede deshacer.',
    labelAceptar: 'Eliminar',
    peligro: true,
  })
  if (!ok) return
  try {
    await apiItems.eliminarVersion(item.value.id, version.numero)
    await cargarVersiones()
    await gestor.cargarEspacio()
  } catch (e) {
    gestor.agregarNotificacion({
      id: 'eliminar-version', tipo: 'error',
      mensaje: mensajeDeAccion(e, 'No se pudo eliminar la versión'), icono: 'pi-trash',
    })
  }
}

// Reproduce o pausa una versión de audio por número.
async function toggleReproducir(numero) {
  if (reproduciendo.value === numero) {
    reproduciendo.value = null
    urlReproduciendo.value = ''
    return
  }
  try {
    const { url } = await apiItems.previsualizarVersion(item.value.id, numero)
    urlReproduciendo.value = url
    reproduciendo.value    = numero
  } catch (e) {
    gestor.agregarNotificacion({
      id: 'preview-version', tipo: 'error',
      mensaje: mensajeDeAccion(e, 'No se pudo cargar la versión para reproducir'), icono: 'pi-headphones',
    })
  }
}

// Cargar versiones al entrar en la pestaña
watch(tabActiva, (tab) => {
  if (tab === 'versiones') cargarVersiones()
})

// Al cambiar de ítem: resetear todo el estado de versiones y reproducción
watch(() => item.value?.id, () => {
  versiones.value = []
  numeroActual.value = 1
  reproduciendo.value = null
  urlReproduciendo.value = ''
  if (tabActiva.value === 'versiones') cargarVersiones()
})


// Mime que se identifican por prefijo (image/png, audio/mp3, etc.)
const TIPOS_POR_PREFIJO = [
  ['image/', 'Imagen'],
  ['video/', 'Vídeo'],
  ['audio/', 'Audio'],
  ['text/', 'Archivo de texto'],
]

// Mimme que no tienen prefijo común: se busca si el mime contiene alguno de los fragmentos
const TIPOS_POR_FRAGMENTO = [
  [['application/pdf'], 'PDF'],
  [['application/msword', 'wordprocessingml'], 'Documento Word'],
  [['application/vnd.ms-excel', 'spreadsheetml'], 'Hoja de cálculo'],
  [['zip', 'tar', 'rar', 'compress'], 'Archivo comprimido'],
]

function tipoLegible(item) {
  if (!item) return ''
  if (item.tipo === 'carpeta') return 'Carpeta'

  const mime = (item.mime_type || '').toLowerCase()

  for (const [prefijo, etiqueta] of TIPOS_POR_PREFIJO) {
    if (mime.startsWith(prefijo)) return etiqueta
  }

  for (const [fragmentos, etiqueta] of TIPOS_POR_FRAGMENTO) {
    if (fragmentos.some(f => mime.includes(f))) return etiqueta
  }

  return 'Archivo'
}


const tieneMetadatos = computed(() =>
  item.value?.metadatos && Object.keys(item.value.metadatos).length > 0,
)
</script>

<template>
  <Teleport to="body" :disabled="esGrande">

    <!-- Backdrop oscuro: solo en móvil cuando el panel está abierto -->
    <Transition name="info-fade">
      <div
        v-if="!esGrande && gestor.panelInfo.visible"
        class="fixed inset-0 bg-black/30 z-40"
        @click="gestor.cerrarPanelInfo()"
      />
    </Transition>

    <!-- Panel principal -->
    <div :class="clasePanel" :style="estiloPanel">
      <div :class="esGrande ? 'w-90 h-full flex flex-col' : 'h-full flex flex-col'">

        <template v-if="item">

          <!-- Cabecera del ítem -->
          <div class="flex items-start gap-3 px-4 py-4 border-b border-surface-200 dark:border-surface-700 shrink-0">
            <i :class="['pi text-3xl mt-0.5 shrink-0', obtenerIcono(item)]" />
            <div class="min-w-0 flex-1">
              <h3 class="font-semibold text-surface-900 dark:text-surface-100 text-sm leading-snug break-all line-clamp-2">
                {{ item.nombre }}
              </h3>
              <p class="text-xs text-surface-500 mt-0.5">
                {{ tipoLegible(item) }}
                <template v-if="item.tipo === 'archivo' && item.tamano_bytes">
                  · {{ formatBytes(item.tamano_bytes) }}
                </template>
              </p>
            </div>
            <button
              @click="gestor.cerrarPanelInfo()"
              class="w-7 h-7 shrink-0 rounded-full flex items-center justify-center
              text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800
              transition-colors cursor-pointer"
              aria-label="Cerrar panel de detalles"
            >
              <i class="pi pi-times text-xs" />
            </button>
          </div>

          <!-- Tabs  -->
          <div class="flex border-b border-surface-200 dark:border-surface-700 shrink-0">
            <button
              @click="tabActiva = 'detalles'"
              :class="[
                'flex-1 py-2.5 text-sm font-medium transition-colors border-b-2',
                tabActiva === 'detalles'
                  ? 'text-primary-600 dark:text-primary-400 border-primary-600 dark:border-primary-400'
                  : 'text-surface-500 dark:text-surface-400 hover:text-surface-800 dark:hover:text-surface-200 border-transparent',
              ]"
            >
              Detalles
            </button>
            <button
              v-if="mostrarPestanaVersiones"
              @click="tabActiva = 'versiones'"
              :class="[
                'flex-1 py-2.5 text-sm font-medium transition-colors border-b-2',
                tabActiva === 'versiones'
                  ? 'text-primary-600 dark:text-primary-400 border-primary-600 dark:border-primary-400'
                  : 'text-surface-500 dark:text-surface-400 hover:text-surface-800 dark:hover:text-surface-200 border-transparent',
              ]"
            >
              Versiones
              <span class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide align-middle
                           bg-primary/15 text-primary-700 dark:text-primary-300">Beta</span>
            </button>
          </div>

          <!-- Contenido scrollable  -->
          <div
            class="flex-1 overflow-y-auto
            [&::-webkit-scrollbar]:w-1.5
            [&::-webkit-scrollbar-track]:bg-transparent
            [&::-webkit-scrollbar-thumb]:rounded-full
            [&::-webkit-scrollbar-thumb]:bg-surface-300
            dark:[&::-webkit-scrollbar-thumb]:bg-surface-600"
          >

            <!--  PESTAÑA: DETALLES  -->
            <div v-if="tabActiva === 'detalles'">
              <section class="px-4 pt-5 pb-4">
                <h4 class="text-xs font-semibold uppercase tracking-wider text-surface-400 dark:text-surface-500 mb-3">
                  Información básica
                </h4>
                <div class="space-y-3">
                  <div class="flex justify-between gap-4 text-sm">
                    <span class="text-surface-500 shrink-0">Tipo</span>
                    <span class="text-surface-800 dark:text-surface-200 text-right">{{ tipoLegible(item) }}</span>
                  </div>
                  <div v-if="item.tipo === 'archivo'" class="flex justify-between gap-4 text-sm">
                    <span class="text-surface-500 shrink-0">Tamaño</span>
                    <span class="text-surface-800 dark:text-surface-200 text-right">{{ formatBytes(item.tamano_bytes) }}</span>
                  </div>
                  <div class="flex justify-between gap-4 text-sm">
                    <span class="text-surface-500 shrink-0">Creado</span>
                    <span class="text-surface-800 dark:text-surface-200 text-right">{{ formatDate(item.fecha_creacion) }}</span>
                  </div>
                  <div class="flex justify-between gap-4 text-sm">
                    <span class="text-surface-500 shrink-0">Modificado</span>
                    <span class="text-surface-800 dark:text-surface-200 text-right">{{ formatDate(item.fecha_modificacion) }}</span>
                  </div>
                </div>
              </section>

              <section v-if="tieneMetadatos" class="px-4 pb-5">
                <div class="border-t border-surface-200 dark:border-surface-700 pt-4 mb-3">
                  <h4 class="text-xs font-semibold uppercase tracking-wider text-surface-400 dark:text-surface-500">
                    Metadatos
                  </h4>
                </div>
                <div class="space-y-3">
                  <div
                    v-for="(valor, clave) in item.metadatos"
                    :key="clave"
                    class="flex justify-between gap-4 text-sm"
                  >
                    <span class="text-surface-500 shrink-0">{{ etiquetaAmigable(clave) }}</span>
                    <span class="text-surface-800 dark:text-surface-200 text-right break-all">{{ valor }}</span>
                  </div>
                </div>
              </section>

              <p
                v-else-if="item.tipo === 'archivo'"
                class="px-4 pb-5 text-xs text-surface-400 dark:text-surface-500 italic"
              >
                No hay metadatos disponibles para este archivo.
              </p>
            </div>

            <!-- PESTAÑA: VERSIONES  -->
            <div v-else-if="tabActiva === 'versiones'">

              <!-- Input oculto para seleccionar archivo -->
              <input
                ref="inputVersion"
                type="file"
                accept="audio/*"
                class="hidden"
                @change="onArchivoSeleccionado"
              />

              <!-- Botón subir nueva versión -->
              <div class="px-4 pt-4 pb-3 border-b border-surface-200 dark:border-surface-700">
                <button
                  @click="iniciarSubidaVersion"
                  class="flex items-center gap-2 w-full justify-center px-3 py-2 rounded-lg text-sm font-medium
                  text-primary-600 dark:text-primary-400
                  border border-primary-300 dark:border-primary-700
                  hover:bg-primary-50 dark:hover:bg-primary-950/30
                  transition-colors cursor-pointer"
                >
                  <i class="pi pi-upload text-xs" />
                  Subir nueva versión
                </button>
              </div>

              <!-- Spinner mientras carga -->
              <div v-if="cargandoVersiones" class="flex justify-center py-8">
                <i class="pi pi-spin pi-spinner text-xl text-surface-400" />
              </div>

              <!-- Lista de versiones -->
              <div v-else class="px-4 py-4 space-y-1">

                <!-- Todas las versiones -->
                <div
                  v-for="version in versiones"
                  :key="version.id"
                  :class="[
                    'rounded-xl p-3 transition-colors',
                    version.es_actual
                      ? 'bg-surface-50 dark:bg-surface-800/60'
                      : 'hover:bg-surface-50 dark:hover:bg-surface-800/40',
                  ]"
                >
                  <div class="flex items-center gap-2 mb-1">
                    <span
                      :class="[
                        'text-xs font-semibold px-1.5 py-0.5 rounded-md',
                        version.es_actual
                          ? 'bg-primary-100 dark:bg-primary-900/50 text-primary-700 dark:text-primary-300'
                          : 'bg-surface-200 dark:bg-surface-700 text-surface-600 dark:text-surface-300',
                      ]"
                    >
                      v{{ version.numero }}
                    </span>
                    <span v-if="version.es_actual" class="text-xs text-surface-500">Versión actual</span>
                  </div>
                  <p class="text-xs text-surface-400 dark:text-surface-500 mb-2">
                    {{ formatDate(version.fecha_creacion) }} · {{ formatBytes(version.tamano_bytes) }}
                  </p>
                  <div class="flex items-center gap-1">
                    <button
                      @click="toggleReproducir(version.numero)"
                      :class="[
                        'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs transition-colors cursor-pointer',
                        reproduciendo === version.numero
                          ? 'bg-pink-100 dark:bg-pink-900/40 text-pink-600 dark:text-pink-300'
                          : 'text-surface-600 dark:text-surface-300 hover:bg-surface-200 dark:hover:bg-surface-700',
                      ]"
                    >
                      <i :class="['pi text-xs', reproduciendo === version.numero ? 'pi-pause' : 'pi-play']" />
                      {{ reproduciendo === version.numero ? 'Pausar' : 'Reproducir' }}
                    </button>
                    <button
                      @click="descargarVersionAntigua(version)"
                      class="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs
                            text-surface-600 dark:text-surface-300
                            hover:bg-surface-200 dark:hover:bg-surface-700
                            transition-colors cursor-pointer"
                    >
                      <i class="pi pi-download text-xs" /> Descargar
                    </button>
                    <button
                      v-if="!version.es_actual"
                      @click="marcarComoActual(version)"
                      class="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs
                            text-surface-600 dark:text-surface-300
                            hover:bg-surface-200 dark:hover:bg-surface-700
                            transition-colors cursor-pointer"
                    >
                      <i class="pi pi-check-circle text-xs" /> Marcar actual
                    </button>
                    <button
                      v-if="!version.es_actual"
                      @click="eliminarVersion(version)"
                      class="ml-auto flex items-center justify-center w-6 h-6 rounded-md text-xs
                            text-surface-400 hover:text-red-500
                            hover:bg-red-50 dark:hover:bg-red-950/30
                            transition-colors cursor-pointer"
                      title="Eliminar esta versión"
                    >
                      <i class="pi pi-trash text-xs" />
                    </button>
                  </div>

                  <div v-if="reproduciendo === version.numero" class="mt-2">
                    <audio
                      controls
                      autoplay
                      :src="urlReproduciendo"
                      class="w-full h-8"
                      style="border-radius: 0.5rem"
                    />
                  </div>
                </div>

                <!-- Sin versiones todavía -->
                <p
                  v-if="versiones.length === 0"
                  class="text-xs text-surface-400 dark:text-surface-500 italic pt-2 text-center"
                >
                  Sube una versión para empezar.
                </p>
              </div>
            </div>

          </div>
        </template>

      </div>
    </div>

  </Teleport>
</template>

<style scoped>
.info-fade-enter-active, .info-fade-leave-active { transition: opacity 0.2s ease; }
.info-fade-enter-from, .info-fade-leave-to { opacity: 0; }
</style>
