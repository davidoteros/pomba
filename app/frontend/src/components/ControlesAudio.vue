<script setup>
// Controles propios sobre el <audio> del navegador: él descarga y reproduce, aquí solo se pinta
import { ref } from 'vue'
import { formatoTiempo as formato, useMedio } from '@/composables/useMedio'
import IconoMedio from '@/components/IconoMedio.vue'
import '@/assets/controles-medio.css'

const props = defineProps({
  src: { type: String, default: null },
  // Cambia al pasar de canción; si cambia solo src (enlace renovado), se sigue por donde iba
  pista: { type: [String, Number], default: null },
  compacto: { type: Boolean, default: false },
  hayAnterior: { type: Boolean, default: false },
  haySiguiente: { type: Boolean, default: false },
})
const emit = defineEmits(['anterior', 'siguiente', 'terminado', 'error'])

const audio = ref(null)
const {
  pausado, cargando, duracion, cargado, silenciado, arrastre, posicion, nivel, iconoVolumen, eventos,
  pct, alternar, irA, saltar, silenciar, alMoverVolumen, alSoltarBarra,
} = useMedio(audio, { src: () => props.src, pista: () => props.pista })

// Como cualquier reproductor: pasados 3 s, "anterior" vuelve al principio de la canción
function anterior() {
  if (audio.value.currentTime > 3 || !props.hayAnterior) audio.value.currentTime = 0
  else emit('anterior')
}

defineExpose({ alternar, saltar, irA, silenciar, anterior })
</script>

<template>
  <div :class="['controles-medio', { 'compacto flex items-center gap-2': compacto }]">
    <audio
      ref="audio"
      :src="src"
      preload="metadata"
      v-on="eventos"
      @ended="emit('terminado')"
      @error="src && emit('error')"
    />

    <!-- Compacto (pestaña Versiones): play, tiempo y barra en una fila -->
    <template v-if="compacto">
      <button
        @click="alternar"
        class="w-8 h-8 shrink-0 rounded-full flex items-center justify-center bg-primary text-primary-contrast
               hover:bg-primary-emphasis transition-colors cursor-pointer"
        :aria-label="pausado ? 'Reproducir' : 'Pausar'"
      >
        <i v-if="cargando && !pausado" class="pi pi-spin pi-spinner text-xs" />
        <IconoMedio v-else :nombre="pausado ? 'play' : 'pausa'" class="size-3.5" :class="{ 'ml-0.5': pausado }" />
      </button>
      <span class="text-xs tabular-nums text-surface-500 dark:text-surface-400">{{ formato(posicion) }}</span>
    </template>

    <input
      type="range"
      class="rango"
      :class="{ 'flex-1 min-w-0': compacto }"
      min="0"
      :max="duracion"
      step="0.1"
      :value="posicion"
      :style="{ '--relleno-hasta': pct(posicion), '--cargado-hasta': pct(cargado) }"
      aria-label="Posición"
      :aria-valuetext="`${formato(posicion)} de ${formato(duracion)}`"
      @input="arrastre = Number($event.target.value)"
      @change="alSoltarBarra"
    />

    <span v-if="compacto" class="text-xs tabular-nums text-surface-500 dark:text-surface-400">{{ formato(duracion) }}</span>

    <!-- Completo (visor): tiempos, anterior / play / siguiente y volumen -->
    <template v-else>
      <div class="flex justify-between mt-0.5 text-xs tabular-nums text-neutral-400">
        <span>{{ formato(posicion) }}</span>
        <span>{{ formato(duracion) }}</span>
      </div>

      <div class="grid grid-cols-[1fr_auto_1fr] items-center mt-2">
        <span />
        <div class="flex items-center gap-4">
          <button
            @click="anterior"
            class="boton w-11 h-11 rounded-full flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer"
            title="Anterior" aria-label="Canción anterior"
          >
            <IconoMedio nombre="anterior" class="size-5.5" />
          </button>
          <button
            @click="alternar"
            class="boton w-14 h-14 rounded-full flex items-center justify-center bg-white text-neutral-950
                   active:scale-95 transition-transform cursor-pointer"
            :aria-label="pausado ? 'Reproducir' : 'Pausar'"
          >
            <i v-if="cargando && !pausado" class="pi pi-spin pi-spinner text-xl" />
            <IconoMedio v-else :nombre="pausado ? 'play' : 'pausa'" class="size-5.5" :class="{ 'ml-0.5': pausado }" />
          </button>
          <button
            @click="emit('siguiente')"
            :disabled="!haySiguiente"
            class="boton w-11 h-11 rounded-full flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer
                   disabled:opacity-30 disabled:cursor-default disabled:hover:bg-transparent"
            title="Siguiente" aria-label="Canción siguiente"
          >
            <IconoMedio nombre="siguiente" class="size-5.5" />
          </button>
        </div>

        <!-- En táctil no: el iPhone no deja cambiar el volumen desde la web, va con sus botones -->
        <div class="justify-self-end flex items-center gap-0.5 pointer-coarse:hidden">
          <button
            @click="silenciar"
            class="boton w-9 h-9 rounded-full flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer"
            :title="silenciado ? 'Quitar silencio (M)' : 'Silenciar (M)'"
            :aria-label="silenciado ? 'Quitar silencio' : 'Silenciar'"
          >
            <IconoMedio :nombre="iconoVolumen" class="size-5" />
          </button>
          <input
            type="range"
            class="rango volumen w-21"
            min="0" max="1" step="0.05"
            :value="nivel"
            :style="{ '--relleno-hasta': `${nivel * 100}%`, '--cargado-hasta': '0%' }"
            aria-label="Volumen"
            @input="alMoverVolumen"
          />
        </div>
      </div>
    </template>
  </div>
</template>
