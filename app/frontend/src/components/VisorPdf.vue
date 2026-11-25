<script setup>
// Visor de PDF con PDF.js (Mozilla), el componente PDFViewer como en su ejemplo "simpleviewer"
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as pdfjsLib from 'pdfjs-dist'
// ?worker: Vite lo empaqueta como un .js (un .mjs suelto no lo sirven bien todos los servidores)
import PdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?worker'
import 'pdfjs-dist/web/pdf_viewer.css'
import BarraVisor from '@/components/BarraVisor.vue'

const props = defineProps({
  url: { type: String, required: true },
  nombre: { type: String, required: true },
})
const emit = defineEmits(['cerrar', 'descargar'])

const contenedor = ref(null)
const hojas = ref(null)
const pagina = ref(1)
const paginas = ref(0)
const zoom = ref(100)
const estado = ref('cargando')

// Fuentes, cmaps, ICC y WebAssembly los copia vite-plugin-static-copy a /pdfjs/
const BASE = `${import.meta.env.BASE_URL}pdfjs/`
let tarea = null
let visor = null
let cerrado = false
let gestos = null
const quitarGestos = new AbortController()

onMounted(async () => {
  // Un solo worker para todos los PDF que se abran
  pdfjsLib.GlobalWorkerOptions.workerPort ??= new PdfWorker()
  // pdf_viewer.mjs lee la librería de globalThis.pdfjsLib: hay que ponerla antes de importarlo
  globalThis.pdfjsLib = pdfjsLib
  const { EventBus, PDFLinkService, PDFViewer } = await import('pdfjs-dist/web/pdf_viewer.mjs')
  if (cerrado) return

  const eventBus = new EventBus()
  const enlaces = new PDFLinkService({ eventBus })
  visor = new PDFViewer({ container: contenedor.value, viewer: hojas.value, eventBus, linkService: enlaces })
  enlaces.setViewer(visor)
  // 'auto': ajusta al ancho sin pasar del 125 %, como Nextcloud
  eventBus.on('pagesinit', () => {
    visor.currentScaleValue = 'auto'
    // Al ajustar el zoom PDF.js pega la página a la barra: volver arriba deja ver el margen
    contenedor.value.scrollTop = 0
  })
  eventBus.on('pagechanging', (e) => { pagina.value = e.pageNumber })
  eventBus.on('scalechanging', (e) => { zoom.value = Math.round(e.scale * 100) })

  // Pellizcar amplía el PDF y no la página entera (TouchManager, el del visor oficial de PDF.js)
  let escala = 1
  gestos = new pdfjsLib.TouchManager({
    container: contenedor.value,
    signal: quitarGestos.signal,
    onPinchStart: () => { escala = visor.currentScale },
    onPinching: (origen, antes, ahora, dx, dy) => {
      escala = Math.min(Math.max(escala * (ahora / antes), 0.25), 10)
      visor.updateScale({ scaleFactor: escala / visor.currentScale, origin: origen, pan: [dx, dy], drawingDelay: 400 })
    },
    onPanning: (dx, dy) => contenedor.value.scrollBy(-dx, -dy),
  })

  tarea = pdfjsLib.getDocument({
    url: props.url,
    cMapUrl: `${BASE}cmaps/`,
    standardFontDataUrl: `${BASE}standard_fonts/`,
    iccUrl: `${BASE}iccs/`,
    wasmUrl: `${BASE}wasm/`,
  })
  try {
    const documento = await tarea.promise
    if (cerrado) return
    paginas.value = documento.numPages
    visor.setDocument(documento)
    enlaces.setDocument(documento)
    estado.value = 'listo'
  } catch (e) {
    if (cerrado) return
    console.error(e)
    estado.value = 'error'
  }
})

// Clic en el fondo gris cierra, como en el visor de fotos: pulsar y soltar ahí sin moverse
// (así no cierra al seleccionar texto ni al arrastrar la barra de scroll)
let pulsadoEnFondo = null
const esFondo = (e) => e.target === contenedor.value || e.target === hojas.value
function alPulsar(e) {
  const caja = contenedor.value.getBoundingClientRect()
  const barra = e.clientX - caja.left >= contenedor.value.clientWidth || e.clientY - caja.top >= contenedor.value.clientHeight
  pulsadoEnFondo = esFondo(e) && !barra ? { x: e.clientX, y: e.clientY } : null
}
function alSoltar(e) {
  const quieto = pulsadoEnFondo && Math.hypot(e.clientX - pulsadoEnFondo.x, e.clientY - pulsadoEnFondo.y) < 6
  if (quieto && esFondo(e)) emit('cerrar')
  pulsadoEnFondo = null
}

onBeforeUnmount(() => {
  cerrado = true
  gestos?.destroy()
  quitarGestos.abort()
  visor?.setDocument(null)
  tarea?.destroy()
})
</script>

<template>
  <div class="visor-pdf flex flex-col h-dvh bg-neutral-800 text-neutral-100 touch-pan-x touch-pan-y">
    <BarraVisor :nombre="nombre" icono="pi-file-pdf text-red-400" @descargar="emit('descargar')" @cerrar="emit('cerrar')">
      <div v-if="estado === 'listo'" class="flex items-center gap-1 text-sm text-neutral-300 tabular-nums">
        <span class="px-1">{{ pagina }} / {{ paginas }}</span>
        <span class="hidden sm:block w-px h-5 bg-neutral-700 mx-1" />
        <button
          @click="visor.decreaseScale()"
          class="hidden sm:flex w-9 h-9 rounded-full items-center justify-center hover:bg-white/10 transition-colors cursor-pointer"
          title="Alejar" aria-label="Alejar"
        >
          <i class="pi pi-search-minus" />
        </button>
        <span class="hidden sm:block w-12 text-center">{{ zoom }} %</span>
        <button
          @click="visor.increaseScale()"
          class="hidden sm:flex w-9 h-9 rounded-full items-center justify-center hover:bg-white/10 transition-colors cursor-pointer"
          title="Acercar" aria-label="Acercar"
        >
          <i class="pi pi-search-plus" />
        </button>
      </div>
    </BarraVisor>

    <!-- PDFViewer pide un contenedor con position: absolute -->
    <div class="relative flex-1">
      <div ref="contenedor" class="absolute inset-0 overflow-auto" @pointerdown="alPulsar" @click="alSoltar">
        <div ref="hojas" class="pdfViewer" />
      </div>
      <div v-if="estado === 'cargando'" class="absolute inset-0 flex items-center justify-center text-neutral-400">
        <i class="pi pi-spin pi-spinner text-2xl" />
      </div>
      <div v-else-if="estado === 'error'" class="absolute inset-0 flex flex-col items-center justify-center gap-2 text-neutral-300">
        <i class="pi pi-exclamation-circle text-2xl" />
        <span class="text-sm">No se pudo abrir el PDF</span>
      </div>
    </div>
  </div>
</template>

<style>
/* Barras de desplazamiento oscuras, como el resto del visor */
.visor-pdf {
  color-scheme: dark;
}
.visor-pdf .pdfViewer {
  --page-margin: 16px auto;
  --page-border: none;
  padding: 16px 0;
}
.visor-pdf .pdfViewer .page {
  box-shadow: 0 2px 16px rgb(0 0 0 / 0.5);
}
</style>
