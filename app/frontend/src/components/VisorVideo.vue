<script setup>
// Vídeo a pantalla completa, a juego con los otros visores: controles encima que se esconden y los vídeos de la lista
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { tinykeys } from 'tinykeys'
import { useMedio } from '@/composables/useMedio'
import { useCerrarEnFondo, useEnlacesFirmados, useFocoAlAbrir, useListaVisor } from '@/composables/useVisor'
import BarraVisor from '@/components/BarraVisor.vue'
import ControlesVideo from '@/components/ControlesVideo.vue'
import IconoMedio from '@/components/IconoMedio.vue'

const props = defineProps({
  videos: { type: Array, required: true },
  inicio: { type: Number, default: 0 },
})
const emit = defineEmits(['cerrar', 'descargar'])

const { indice, actual, hayAnterior, haySiguiente, contador, anterior, siguiente } = useListaVisor(() => props.videos, props.inicio)

// Además de url y error, cada enlace guarda el código del fallo del <video> (codigo)
const { enlaces, pedir, reintentar } = useEnlacesFirmados('No se pudo abrir el vídeo.')
const enlace = computed(() => enlaces[actual.value.id])
watch(actual, (item) => pedir(item), { immediate: true })

const video = ref(null)
const m = reactive(useMedio(video, { src: () => enlace.value?.url, pista: () => actual.value.id }))

// El enlace caduca a los 5 min: si falla, se pide otro una vez y se sigue por donde iba; si vuelve a fallar, aviso
async function alFallar(e) {
  const codigo = e.target.error?.code ?? 0
  const item = actual.value
  const antes = enlaces[item.id]
  if (!antes?.url) return
  if (!(await reintentar(item))) { antes.codigo = codigo; return }
  // Mismo enlace (la demo da siempre el mismo): no se recargaría, así que el aviso ya
  const ahora = enlaces[item.id]
  if (ahora.url === antes.url && !ahora.error) ahora.codigo = codigo
}

// 3 = no se puede descodificar, 4 = formato no soportado (AV1 sin chip, HEVC…) o archivo dañado
const aviso = computed(() => {
  const en = enlace.value
  if (en?.error) return { titulo: en.error, texto: '' }
  if (en?.codigo == null) return null
  if (en.codigo === 3 || en.codigo === 4) {
    return {
      titulo: 'Este vídeo no se puede abrir aquí',
      texto: 'Puede que este navegador no admita su formato o que el archivo esté dañado. '
        + 'Descárgalo para verlo con otro reproductor.',
    }
  }
  return { titulo: 'No se pudo cargar el vídeo.', texto: 'Comprueba la conexión e inténtalo de nuevo.' }
})

// Se oye pero no se ve: el navegador no sabe descodificar la imagen y no da error (lo avisa igual Nextcloud)
const soloSonido = ref(false)
watch(actual, () => { soloSonido.value = false })
const alCargarDatos = (e) => { soloSonido.value = e.target.videoWidth === 0 }

// Controles que se esconden: tras 2,5 s sin mover el ratón si está sonando y el teclado no está en ellos
const raiz = useFocoAlAbrir()
const quieto = ref(false)
let temporizador = null
let arrastrando = false
function mostrar() {
  quieto.value = false
  clearTimeout(temporizador)
  temporizador = setTimeout(() => {
    const foco = document.activeElement
    const tecladoDentro = raiz.value?.contains(foco) && foco !== raiz.value && foco.matches(':focus-visible')
    if (!m.pausado && !aviso.value && !tecladoDentro && !arrastrando) quieto.value = true
  }, 2500)
}
watch(() => m.pausado, mostrar)
const alMoverPuntero = (e) => { if (e.pointerType === 'mouse') mostrar() }
const alPulsarControles = () => { arrastrando = true; mostrar() }
const alSoltarPuntero = () => { if (arrastrando) { arrastrando = false; mostrar() } }
window.addEventListener('pointerup', alSoltarPuntero)

// Pantalla completa del visor entero (con nuestros controles); en el iPhone no existe y se usa la del vídeo
const enCompleta = ref(false)
const elementoCompleto = () => document.fullscreenElement ?? document.webkitFullscreenElement ?? null
function alCambiarCompleta() { enCompleta.value = elementoCompleto() === raiz.value }
document.addEventListener('fullscreenchange', alCambiarCompleta)
document.addEventListener('webkitfullscreenchange', alCambiarCompleta)

function pantallaCompleta() {
  if (elementoCompleto()) {
    (document.exitFullscreen ?? document.webkitExitFullscreen).call(document)
    return
  }
  const r = raiz.value
  if (document.fullscreenEnabled) r.requestFullscreen().catch(() => {})
  else if (document.webkitFullscreenEnabled) r.webkitRequestFullscreen()
  else video.value?.webkitEnterFullscreen?.()
}

// Ratón: clic = play/pausa, doble clic = pantalla completa. Dedo: toque = enseñar/esconder, doble toque a un lado = ±10 s
const salto = ref(null) // -1 o 1 mientras se ve el "−10 s" / "+10 s"
let tipoPuntero = 'mouse'
let ultimoToque = 0
let temporizadorToque = null
function alTocarVideo(e) {
  if (tipoPuntero !== 'touch') {
    if (e.detail === 2) pantallaCompleta()
    m.alternar() // en el doble clic el segundo deshace el primero
    return
  }
  const ahora = Date.now()
  const r = e.currentTarget.getBoundingClientRect()
  const lado = e.clientX < r.left + r.width / 3 ? -1 : e.clientX > r.right - r.width / 3 ? 1 : 0
  clearTimeout(temporizadorToque)
  if (lado && ahora - ultimoToque < 300) {
    m.saltar(lado * 10)
    salto.value = lado
    setTimeout(() => { salto.value = null }, 450)
  } else {
    temporizadorToque = setTimeout(() => {
      if (quieto.value || m.pausado) mostrar()
      else { clearTimeout(temporizador); quieto.value = true }
    }, 300)
  }
  ultimoToque = ahora
}

// Clic en el fondo cierra, como en los otros visores (en pantalla completa no)
const fondo = ref(null)
const { alPulsar, alSoltar } = useCerrarEnFondo((e) => e.target === fondo.value && !enCompleta.value, () => emit('cerrar'))

// Teclado: espacio y K, ← → 5 s, M, F y Mayús + N / P (Esc ya lo cierra el diálogo)
const en = (e, sel) => e.target.matches?.(sel)
function tecla(fn) {
  return (e) => { fn(e); mostrar() }
}
const quitarTeclas = tinykeys(window, {
  Space: tecla((e) => { if (en(e, 'button')) return; e.preventDefault(); m.alternar() }),
  k: tecla(() => m.alternar()),
  ArrowLeft: tecla((e) => { if (en(e, '.volumen')) return; e.preventDefault(); m.saltar(-5) }),
  ArrowRight: tecla((e) => { if (en(e, '.volumen')) return; e.preventDefault(); m.saltar(5) }),
  m: tecla(() => m.silenciar()),
  f: tecla(() => pantallaCompleta()),
  'Shift+KeyN': tecla(siguiente),
  'Shift+KeyP': tecla(anterior),
}, {
  // tinykeys ignora por defecto todo <input> y las teclas mantenidas: aquí las barras sí, y mantener → avanza seguido
  ignore: (e) => e.isComposing || e.target.matches?.('[contenteditable],select,textarea,input:not([type=range])'),
})

onMounted(mostrar)

onBeforeUnmount(() => {
  quitarTeclas()
  clearTimeout(temporizador)
  clearTimeout(temporizadorToque)
  window.removeEventListener('pointerup', alSoltarPuntero)
  document.removeEventListener('fullscreenchange', alCambiarCompleta)
  document.removeEventListener('webkitfullscreenchange', alCambiarCompleta)
  if (elementoCompleto()) (document.exitFullscreen ?? document.webkitExitFullscreen).call(document)
})
</script>

<template>
  <!-- Sin pellizcar: ampliaría la aplicación entera -->
  <div
    ref="raiz"
    tabindex="-1"
    class="relative flex flex-col h-dvh bg-neutral-900 text-neutral-100 select-none outline-none [color-scheme:dark] touch-pan-x touch-pan-y"
    :class="{ 'cursor-none': quieto }"
    @pointermove="alMoverPuntero"
    @focusin="mostrar"
  >
    <!-- En pantalla completa la barra también va encima y se esconde -->
    <div
      class="transition-opacity duration-250"
      :class="[enCompleta && 'absolute inset-x-0 top-0 z-20', enCompleta && quieto && 'opacity-0 pointer-events-none']"
    >
      <BarraVisor :nombre="actual.nombre" icono="pi-video text-sky-400" @descargar="emit('descargar', actual)" @cerrar="emit('cerrar')">
        <span v-if="contador" class="px-1 text-sm text-neutral-300 tabular-nums max-[480px]:hidden">{{ contador }}</span>
      </BarraVisor>
    </div>

    <div
      ref="fondo"
      class="relative flex-1 min-h-0 flex items-center justify-center overflow-hidden"
      @pointerdown="alPulsar"
      @click="alSoltar"
    >
      <!-- No se puede reproducir: aviso claro en vez de pantalla negra -->
      <template v-if="aviso">
        <div role="alert" class="max-w-[420px] mx-4 text-center bg-neutral-800 rounded-2xl p-6 shadow-[0_2px_16px_rgb(0_0_0/0.5)]">
          <i class="pi pi-exclamation-circle text-3xl text-amber-400" />
          <h2 class="mt-2.5 text-[17px] font-semibold">{{ aviso.titulo }}</h2>
          <p v-if="aviso.texto" class="mt-1.5 text-sm leading-normal text-neutral-300">{{ aviso.texto }}</p>
          <button
            @click="emit('descargar', actual)"
            class="boton mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white text-neutral-950 text-sm font-semibold
                   cursor-pointer active:scale-95 transition-transform"
          >
            <i class="pi pi-download" /> Descargar
          </button>
        </div>
        <div v-if="videos.length > 1" class="controles-medio absolute inset-x-0 bottom-0 flex justify-center gap-2 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
          <button
            @click="anterior" :disabled="!hayAnterior"
            class="boton w-11 h-11 rounded-full flex items-center justify-center hover:bg-white/10 cursor-pointer disabled:opacity-30 disabled:cursor-default"
            title="Vídeo anterior (Mayús + P)" aria-label="Vídeo anterior"
          >
            <IconoMedio nombre="anterior" class="size-5" />
          </button>
          <button
            @click="siguiente" :disabled="!haySiguiente"
            class="boton w-11 h-11 rounded-full flex items-center justify-center hover:bg-white/10 cursor-pointer disabled:opacity-30 disabled:cursor-default"
            title="Vídeo siguiente (Mayús + N)" aria-label="Vídeo siguiente"
          >
            <IconoMedio nombre="siguiente" class="size-5" />
          </button>
        </div>
      </template>

      <div v-show="!aviso" class="relative">
        <video
          ref="video"
          :src="enlace?.url"
          playsinline
          preload="metadata"
          class="block bg-black outline-none"
          :class="enCompleta ? 'w-screen h-dvh object-contain' : 'max-w-[100vw] max-h-[calc(100dvh-3rem)]'"
          v-on="m.eventos"
          @loadedmetadata="alCargarDatos"
          @error="alFallar"
          @pointerdown="tipoPuntero = $event.pointerType"
          @click="alTocarVideo"
        />

        <i
          v-if="!enlace?.url || (m.cargando && !m.pausado)"
          class="pi pi-spin pi-spinner text-3xl text-white absolute left-1/2 top-1/2 -translate-1/2 pointer-events-none"
        />

        <!-- El de los controles ya lo lee el lector de pantalla: este solo es para el ratón y el dedo -->
        <button
          v-if="m.pausado && enlace?.url && !m.cargando"
          tabindex="-1" aria-hidden="true"
          class="absolute left-1/2 top-1/2 -translate-1/2 size-17 rounded-full flex items-center justify-center bg-black/55
                 backdrop-blur-sm cursor-pointer active:scale-95 transition-[opacity,transform]"
          :class="{ 'opacity-0 pointer-events-none': quieto }"
          @click="m.alternar"
        >
          <IconoMedio :nombre="m.terminado ? 'otra-vez' : 'play'" class="size-7" :class="{ 'ml-1': !m.terminado }" />
        </button>

        <span
          v-if="salto"
          aria-hidden="true"
          class="absolute top-1/2 -translate-y-1/2 px-4 py-2.5 rounded-full bg-black/55 text-sm font-semibold pointer-events-none"
          :class="salto < 0 ? 'left-[12%]' : 'right-[12%]'"
        >{{ salto < 0 ? '−10 s' : '+10 s' }}</span>

        <p
          v-if="soloSonido"
          role="status"
          class="absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/70 text-[13px] whitespace-nowrap"
        >
          <i class="pi pi-exclamation-circle text-amber-400" /> Este navegador no puede mostrar la imagen de este vídeo; solo se oye.
        </p>

        <ControlesVideo
          class="absolute inset-x-0 bottom-0 transition-opacity duration-250"
          :class="{ 'opacity-0 pointer-events-none': quieto }"
          :m="m"
          :hay-anterior="hayAnterior"
          :hay-siguiente="haySiguiente"
          :en-completa="enCompleta"
          :contador="contador"
          @anterior="anterior"
          @siguiente="siguiente"
          @completa="pantallaCompleta"
          @pointerdown="alPulsarControles"
        />
      </div>
    </div>

    <p class="sr-only" aria-live="polite">Vídeo {{ indice + 1 }} de {{ videos.length }}: {{ actual.nombre }}</p>
  </div>
</template>
