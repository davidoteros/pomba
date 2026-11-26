<script setup>
// Imágenes a pantalla completa: se pasa de una a otra con las flechas, ← → o deslizando (Embla)
import { onBeforeUnmount, watch } from 'vue'
import emblaCarouselVue from 'embla-carousel-vue'
import { tinykeys } from 'tinykeys'
import { useCerrarEnFondo, useEnlacesFirmados, useFocoAlAbrir, useListaVisor } from '@/composables/useVisor'
import { obtenerIcono } from '@/utils/iconos'
import BarraVisor from '@/components/BarraVisor.vue'

const props = defineProps({
  imagenes: { type: Array, required: true },
  inicio: { type: Number, default: 0 },
})
const emit = defineEmits(['cerrar', 'descargar'])

// Quien mueve el índice es el carrusel; anterior / siguiente van por él
const { indice, actual, hayAnterior, haySiguiente, contador } = useListaVisor(() => props.imagenes, props.inicio)
const raiz = useFocoAlAbrir()

// Al final se para (como Drive y Google Fotos)
const [emblaRef, emblaApi] = emblaCarouselVue({ startIndex: props.inicio, duration: 22 })
watch(emblaApi, (api) => api?.on('select', () => { indice.value = api.selectedScrollSnap() }))

// Además de url y error, cada foto guarda si ya se ha pintado (cargada)
const { enlaces: fotos, pedir, reintentar } = useEnlacesFirmados('No se pudo abrir la imagen.')

// Como Nextcloud: primero la que se ve y después sus vecinas
watch(indice, async (i) => {
  await pedir(props.imagenes[i])
  pedir(props.imagenes[i - 1])
  pedir(props.imagenes[i + 1])
}, { immediate: true })

// La URL firmada caduca a los 5 min: si falla, se pide otra una vez
async function alFallar(item) {
  if (!(await reintentar(item))) fotos[item.id].error = 'No se pudo abrir la imagen.'
}

// Clic en el fondo de la diapositiva cierra; si arrastras para pasar de foto, no
const { alPulsar, alSoltar } = useCerrarEnFondo((e) => e.target === e.currentTarget, () => emit('cerrar'))

const cerca = (i) => Math.abs(i - indice.value) <= 1
const anterior = () => emblaApi.value?.scrollPrev()
const siguiente = () => emblaApi.value?.scrollNext()

const quitarTeclas = tinykeys(window, { ArrowLeft: anterior, ArrowRight: siguiente })
onBeforeUnmount(quitarTeclas)
</script>

<template>
  <!-- Sin pellizcar: ampliaría la aplicación entera (el zoom de fotos, más adelante) -->
  <div ref="raiz" tabindex="-1" class="flex flex-col h-dvh bg-neutral-900 text-neutral-100 select-none outline-none [color-scheme:dark] touch-pan-x touch-pan-y">
    <BarraVisor :nombre="actual.nombre" :icono="obtenerIcono(actual)" @descargar="emit('descargar', actual)" @cerrar="emit('cerrar')">
      <span v-if="contador" class="px-1 text-sm text-neutral-300 tabular-nums">{{ contador }}</span>
    </BarraVisor>

    <div class="relative flex-1">
      <div ref="emblaRef" class="absolute inset-0 overflow-hidden">
        <div class="flex h-full touch-pan-y">
          <div v-for="(item, i) in imagenes" :key="item.id" class="relative flex-[0_0_100%] min-w-0">
            <div v-if="cerca(i)" class="absolute inset-0 flex items-center justify-center p-4" @pointerdown="alPulsar" @click="alSoltar">
              <img
                v-if="fotos[item.id]?.url && !fotos[item.id].error"
                :src="fotos[item.id].url"
                :alt="item.nombre"
                draggable="false"
                class="max-w-full max-h-full object-contain shadow-[0_2px_16px_rgb(0_0_0/0.5)]"
                @load="fotos[item.id].cargada = true"
                @error="alFallar(item)"
              />
              <div v-if="fotos[item.id]?.error" class="flex flex-col items-center gap-2 text-neutral-300 text-center">
                <i class="pi pi-exclamation-circle text-2xl" />
                <span class="text-sm">{{ fotos[item.id].error }}</span>
              </div>
              <i v-else-if="!fotos[item.id]?.cargada" class="pi pi-spin pi-spinner text-2xl text-neutral-400 absolute" />
            </div>
          </div>
        </div>
      </div>

      <!-- En táctil solo se desliza: sin flechas -->
      <button
        v-if="hayAnterior"
        @click="anterior"
        class="absolute left-4 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full flex items-center justify-center
               bg-black/45 hover:bg-black/75 transition-colors cursor-pointer outline-none
               focus-visible:ring-2 focus-visible:ring-white/60 pointer-coarse:hidden"
        title="Anterior" aria-label="Imagen anterior"
      >
        <i class="pi pi-chevron-left" />
      </button>
      <button
        v-if="haySiguiente"
        @click="siguiente"
        class="absolute right-4 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full flex items-center justify-center
               bg-black/45 hover:bg-black/75 transition-colors cursor-pointer outline-none
               focus-visible:ring-2 focus-visible:ring-white/60 pointer-coarse:hidden"
        title="Siguiente" aria-label="Imagen siguiente"
      >
        <i class="pi pi-chevron-right" />
      </button>
    </div>
  </div>
</template>
