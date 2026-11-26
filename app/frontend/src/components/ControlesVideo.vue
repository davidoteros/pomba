<script setup>
// Controles del visor de vídeo, encima de la imagen; el estado y las acciones vienen de useMedio (en reactive)
import { formatoTiempo as formato } from '@/composables/useMedio'
import IconoMedio from '@/components/IconoMedio.vue'
import '@/assets/controles-medio.css'

const props = defineProps({
  m: { type: Object, required: true },
  hayAnterior: { type: Boolean, default: false },
  haySiguiente: { type: Boolean, default: false },
  enCompleta: { type: Boolean, default: false },
  contador: { type: String, default: '' },
})
const emit = defineEmits(['anterior', 'siguiente', 'completa'])

const etiquetaPlay = () => (props.m.terminado ? 'Volver a ver' : props.m.pausado ? 'Reproducir' : 'Pausar')
const iconoPlay = () => (props.m.terminado ? 'otra-vez' : props.m.pausado ? 'play' : 'pausa')
</script>

<template>
  <div class="controles-medio px-3 pt-7 pb-[calc(0.625rem+env(safe-area-inset-bottom))] bg-[linear-gradient(to_top,rgb(0_0_0/0.75),rgb(0_0_0/0.35)_60%,transparent)]">
    <input
      type="range"
      class="rango"
      min="0"
      :max="m.duracion"
      step="0.1"
      :value="m.posicion"
      :style="{ '--relleno-hasta': m.pct(m.posicion), '--cargado-hasta': m.pct(m.cargado) }"
      aria-label="Posición"
      :aria-valuetext="`${formato(m.posicion)} de ${formato(m.duracion)}`"
      @input="m.arrastre = Number($event.target.value)"
      @change="m.alSoltarBarra"
    />

    <div class="flex items-center gap-1 mt-1">
      <button
        @click="emit('anterior')"
        :disabled="!hayAnterior"
        class="boton w-9 h-9 rounded-full flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer
               disabled:opacity-30 disabled:cursor-default disabled:hover:bg-transparent"
        title="Vídeo anterior (Mayús + P)" aria-label="Vídeo anterior"
      >
        <IconoMedio nombre="anterior" class="size-5" />
      </button>
      <button
        @click="m.alternar"
        class="boton w-11 h-11 rounded-full flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer"
        :title="`${etiquetaPlay()} (espacio)`" :aria-label="etiquetaPlay()"
      >
        <i v-if="m.cargando && !m.pausado" class="pi pi-spin pi-spinner text-lg" />
        <IconoMedio v-else :nombre="iconoPlay()" class="size-5.5" />
      </button>
      <button
        @click="emit('siguiente')"
        :disabled="!haySiguiente"
        class="boton w-9 h-9 rounded-full flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer
               disabled:opacity-30 disabled:cursor-default disabled:hover:bg-transparent"
        title="Vídeo siguiente (Mayús + N)" aria-label="Vídeo siguiente"
      >
        <IconoMedio nombre="siguiente" class="size-5" />
      </button>
      <span class="ml-1.5 text-[13px] tabular-nums text-neutral-300 whitespace-nowrap">
        {{ formato(m.posicion) }} / {{ formato(m.duracion) }}
      </span>

      <span class="flex-1" />

      <!-- En pantallas estrechas el contador no cabe en la barra negra -->
      <span v-if="contador" class="mr-1 text-[13px] tabular-nums text-neutral-400 whitespace-nowrap min-[481px]:hidden">{{ contador }}</span>
      <button
        @click="m.silenciar"
        class="boton w-9 h-9 rounded-full flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer"
        :title="m.silenciado ? 'Quitar silencio (M)' : 'Silenciar (M)'"
        :aria-label="m.silenciado ? 'Quitar silencio' : 'Silenciar'"
      >
        <IconoMedio :nombre="m.iconoVolumen" class="size-5" />
      </button>
      <!-- En táctil no: el iPhone no deja cambiar el volumen desde la web -->
      <span class="pointer-coarse:hidden">
        <input
          type="range"
          class="rango volumen"
          min="0" max="1" step="0.05"
          :value="m.nivel"
          :style="{ '--relleno-hasta': `${m.nivel * 100}%`, '--cargado-hasta': '0%' }"
          aria-label="Volumen"
          @input="m.alMoverVolumen"
        />
      </span>
      <button
        @click="emit('completa')"
        class="boton w-9 h-9 rounded-full flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer"
        :title="enCompleta ? 'Salir de pantalla completa (F)' : 'Pantalla completa (F)'"
        :aria-label="enCompleta ? 'Salir de pantalla completa' : 'Pantalla completa'"
      >
        <IconoMedio :nombre="enCompleta ? 'salir-completa' : 'pantalla-completa'" class="size-5" />
      </button>
    </div>
  </div>
</template>
