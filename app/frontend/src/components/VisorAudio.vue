<script setup>
// Audio a pantalla completa, a juego con los visores de fotos y PDF: carátula, controles y las canciones de la lista
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { tinykeys } from 'tinykeys'
import { apiItems } from '@/api/items'
import { useCerrarEnFondo, useEnlacesFirmados, useFocoAlAbrir, useListaVisor } from '@/composables/useVisor'
import BarraVisor from '@/components/BarraVisor.vue'
import ControlesAudio from '@/components/ControlesAudio.vue'

const props = defineProps({
  pistas: { type: Array, required: true },
  inicio: { type: Number, default: 0 },
  portadas: { type: Object, default: () => ({}) }, // id de carpeta - imagen portada/cover/folder
  carpeta: { type: Object, default: null },        // la que enseña la tabla: { id, label }
})
const emit = defineEmits(['cerrar', 'descargar'])

const { actual, hayAnterior, haySiguiente, contador, anterior, siguiente } = useListaVisor(() => props.pistas, props.inicio)
const titulo = computed(() => actual.value.nombre.replace(/\.[^.]+$/, ''))
const nombreCarpeta = computed(() => {
  if (!props.carpeta || props.carpeta.id !== actual.value.padre) return ''
  return props.carpeta.id === null ? 'Mi unidad' : props.carpeta.label
})

const controles = ref(null)

const raiz = useFocoAlAbrir()

const { enlaces, pedir, reintentar } = useEnlacesFirmados('No se pudo abrir el audio.')
watch(actual, (item) => pedir(item), { immediate: true })

// Tras una pausa larga el enlace caduca: se pide otro una vez y se sigue por donde iba
async function alFallar() {
  const item = actual.value
  if (!(await reintentar(item))) enlaces[item.id].error = 'No se pudo abrir el audio.'
}

// Carátula: la imagen original
const caratulas = reactive({})
const portada = computed(() => props.portadas[actual.value.padre] ?? null)
const urlCaratula = computed(() => (portada.value ? caratulas[portada.value.id] : null))
watch(portada, async (p) => {
  if (!p || p.id in caratulas) return
  caratulas[p.id] = null
  try {
    caratulas[p.id] = (await apiItems.previsualizar(p.id)).url
  } catch {
    // Sin carátula: se quedan los auriculares
  }
}, { immediate: true })

// Clic en el fondo cierra, como en los otros visores
const fondo = ref(null)
const { alPulsar, alSoltar } = useCerrarEnFondo((e) => e.target === fondo.value, () => emit('cerrar'))

// Teclado: espacio, ← → 5 s y M (Esc ya lo cierra el diálogo)
const enVolumen = (e) => e.target.matches?.('.volumen')
const quitarTeclas = tinykeys(window, {
  Space: (e) => { e.preventDefault(); controles.value?.alternar() },
  ArrowLeft: (e) => { if (enVolumen(e)) return; e.preventDefault(); controles.value?.saltar(-5) },
  ArrowRight: (e) => { if (enVolumen(e)) return; e.preventDefault(); controles.value?.saltar(5) },
  m: () => controles.value?.silenciar(),
})

// Media Session: controles en la pantalla de bloqueo del móvil y teclas multimedia del teclado
const sesion = 'mediaSession' in navigator ? navigator.mediaSession : null
const acciones = {
  play: () => controles.value?.alternar(),
  pause: () => controles.value?.alternar(),
  previoustrack: () => controles.value?.anterior(),
  nexttrack: siguiente,
  seekto: (d) => controles.value?.irA(d.seekTime),
}
if (sesion) {
  for (const [accion, fn] of Object.entries(acciones)) {
    try { sesion.setActionHandler(accion, fn) } catch { }
  }
  watch([titulo, nombreCarpeta, urlCaratula], () => {
    sesion.metadata = new MediaMetadata({
      title: titulo.value,
      album: nombreCarpeta.value,
      artwork: urlCaratula.value ? [{ src: urlCaratula.value }] : [],
    })
  }, { immediate: true })
}

onBeforeUnmount(() => {
  quitarTeclas()
  if (!sesion) return
  sesion.metadata = null
  for (const accion of Object.keys(acciones)) {
    try { sesion.setActionHandler(accion, null) } catch {}
  }
})
</script>

<template>
  <!-- Sin pellizcar: ampliaría la aplicación entera -->
  <div ref="raiz" tabindex="-1" class="flex flex-col h-dvh bg-neutral-900 text-neutral-100 select-none outline-none [color-scheme:dark] touch-pan-x touch-pan-y">
    <BarraVisor :nombre="actual.nombre" icono="pi-headphones text-pink-400" @descargar="emit('descargar', actual)" @cerrar="emit('cerrar')">
      <span v-if="contador" class="px-1 text-sm text-neutral-300 tabular-nums">{{ contador }}</span>
    </BarraVisor>

    <div
      ref="fondo"
      class="flex-1 min-h-0 flex flex-col items-center justify-center gap-5 px-4 pt-4 pb-[calc(1.5rem+env(safe-area-inset-bottom))]"
      @pointerdown="alPulsar"
      @click="alSoltar"
    >
      <div
        class="w-[min(340px,72vw,42dvh)] aspect-square shrink-0 rounded-xl overflow-hidden bg-neutral-800
               flex items-center justify-center shadow-[0_2px_16px_rgb(0_0_0/0.5)]"
      >
        <img v-if="urlCaratula" :src="urlCaratula" alt="" draggable="false" class="size-full object-cover" />
        <i v-else class="pi pi-headphones text-pink-400 text-7xl" />
      </div>

      <div class="max-w-[min(560px,92vw)] min-w-0 text-center">
        <h2 class="text-xl font-semibold truncate">{{ titulo }}</h2>
        <p v-if="nombreCarpeta" class="mt-1 text-sm text-neutral-400 truncate">{{ nombreCarpeta }}</p>
      </div>

      <p v-if="enlaces[actual.id]?.error" class="flex items-center gap-2 text-sm text-neutral-300">
        <i class="pi pi-exclamation-circle" /> {{ enlaces[actual.id].error }}
      </p>

      <ControlesAudio
        ref="controles"
        class="w-[min(560px,92vw)]"
        :src="enlaces[actual.id]?.url"
        :pista="actual.id"
        :hay-anterior="hayAnterior"
        :hay-siguiente="haySiguiente"
        @anterior="anterior"
        @siguiente="siguiente"
        @terminado="siguiente"
        @error="alFallar"
      />
    </div>
  </div>
</template>
