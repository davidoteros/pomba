<script setup>
// Controles propios sobre el <audio> del navegador: él descarga y reproduce, aquí solo se pinta
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import IconoAudio from '@/components/IconoAudio.vue'

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
const pausado = ref(true)
const cargando = ref(false)
const tiempo = ref(0)
const duracion = ref(0)
const cargado = ref(0)
const volumen = ref(1)
const silenciado = ref(false)
const arrastre = ref(null) // posición mientras se arrastra la barra, sin mover aún el audio

// Otra canción: se para la anterior mientras llega su enlace y la barra vuelve a cero
watch(() => props.pista, () => {
  audio.value?.pause()
  tiempo.value = 0
  duracion.value = 0
  cargado.value = 0
})

// Enlace nuevo: si es de otra canción suena desde el principio; si es la misma (renovado), por donde iba
let pistaDelEnlace = null
let reanudarEn = null
function alLlegarEnlace(src) {
  if (!src) return
  const misma = pistaDelEnlace === props.pista
  reanudarEn = misma ? tiempo.value : null
  pistaDelEnlace = props.pista
  if (!misma || !pausado.value) audio.value.play().catch(() => {})
}
// 'post': cuando el <audio> ya tiene el src nuevo; el primero, al montarse (antes no existe el <audio>)
watch(() => props.src, alLlegarEnlace, { flush: 'post' })
onMounted(() => alLlegarEnlace(props.src))

// Los eventos usan e.target: al cerrar, el <audio> aún avisa cuando la referencia ya es null
function alCargarDatos(e) {
  duracion.value = e.target.duration || 0
  if (reanudarEn !== null) e.target.currentTime = reanudarEn
  reanudarEn = null
}

function alAvanzar(e) {
  const a = e.target
  tiempo.value = a.currentTime
  if (a.buffered.length) cargado.value = a.buffered.end(a.buffered.length - 1)
}

// Al cerrar, cortar también la descarga (quitar el <audio> de la página no la para)
onBeforeUnmount(() => {
  audio.value.pause()
  audio.value.removeAttribute('src')
  audio.value.load()
})

const posicion = computed(() => arrastre.value ?? tiempo.value)
const pct = (s) => (duracion.value ? `${Math.min((s / duracion.value) * 100, 100)}%` : '0%')

function formato(s) {
  if (!Number.isFinite(s) || s < 0) s = 0
  s = Math.floor(s)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const seg = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${seg}` : `${m}:${seg}`
}

function alternar() {
  if (!audio.value?.src) return
  if (audio.value.paused) audio.value.play().catch(() => {})
  else audio.value.pause()
}

function saltar(segundos) {
  if (!duracion.value) return
  audio.value.currentTime = Math.min(Math.max(audio.value.currentTime + segundos, 0), duracion.value)
}

function irA(segundos) {
  if (duracion.value) audio.value.currentTime = Math.min(Math.max(segundos, 0), duracion.value)
}

// Como cualquier reproductor: pasados 3 s, "anterior" vuelve al principio de la canción
function anterior() {
  if (audio.value.currentTime > 3 || !props.hayAnterior) audio.value.currentTime = 0
  else emit('anterior')
}

function silenciar() {
  audio.value.muted = !audio.value.muted
  if (!audio.value.muted && audio.value.volume === 0) audio.value.volume = 1
}

function alMoverVolumen(e) {
  const v = Number(e.target.value)
  audio.value.volume = v
  audio.value.muted = v === 0
}

function alCambiarVolumen() {
  volumen.value = audio.value.volume
  silenciado.value = audio.value.muted
}

const nivel = computed(() => (silenciado.value ? 0 : volumen.value))
const iconoVolumen = computed(() => (nivel.value === 0 ? 'silencio' : nivel.value < 0.5 ? 'volumen-bajo' : 'volumen-alto'))

function alSoltarBarra(e) {
  irA(Number(e.target.value))
  arrastre.value = null
}

defineExpose({ alternar, saltar, irA, silenciar, anterior })
</script>

<template>
  <div :class="['controles-audio', { 'compacto flex items-center gap-2': compacto }]">
    <audio
      ref="audio"
      :src="src"
      preload="metadata"
      @loadedmetadata="alCargarDatos"
      @durationchange="duracion = $event.target.duration || 0"
      @timeupdate="alAvanzar"
      @progress="alAvanzar"
      @play="pausado = false"
      @pause="pausado = true"
      @waiting="cargando = true"
      @loadstart="cargando = !!src"
      @canplay="cargando = false"
      @playing="cargando = false"
      @volumechange="alCambiarVolumen"
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
        <IconoAudio v-else :nombre="pausado ? 'play' : 'pausa'" class="size-3.5" :class="{ 'ml-0.5': pausado }" />
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
            <IconoAudio nombre="anterior" class="size-5.5" />
          </button>
          <button
            @click="alternar"
            class="boton w-14 h-14 rounded-full flex items-center justify-center bg-white text-neutral-950
                   active:scale-95 transition-transform cursor-pointer"
            :aria-label="pausado ? 'Reproducir' : 'Pausar'"
          >
            <i v-if="cargando && !pausado" class="pi pi-spin pi-spinner text-xl" />
            <IconoAudio v-else :nombre="pausado ? 'play' : 'pausa'" class="size-5.5" :class="{ 'ml-0.5': pausado }" />
          </button>
          <button
            @click="emit('siguiente')"
            :disabled="!haySiguiente"
            class="boton w-11 h-11 rounded-full flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer
                   disabled:opacity-30 disabled:cursor-default disabled:hover:bg-transparent"
            title="Siguiente" aria-label="Canción siguiente"
          >
            <IconoAudio nombre="siguiente" class="size-5.5" />
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
            <IconoAudio :nombre="iconoVolumen" class="size-5" />
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

<style>
/* Visor: blanco sobre negro, como el resto de visores */
.controles-audio {
  --relleno: #fff;
  --cargado: #737373;
  --pista: #404040;
}
/* Versiones: con los colores del tema */
.controles-audio.compacto {
  --relleno: var(--p-primary-color);
  --cargado: var(--p-surface-400);
  --pista: var(--p-surface-200);
}
.dark .controles-audio.compacto {
  --cargado: var(--p-surface-500);
  --pista: var(--p-surface-700);
}

/* La barra es un <input type="range"> del navegador: teclado y lectores de pantalla de serie */
.controles-audio .rango {
  appearance: none;
  -webkit-appearance: none;
  display: block;
  width: 100%;
  height: 20px;
  margin: 0;
  background: transparent;
  cursor: pointer;
  touch-action: none;
}
.controles-audio .rango.volumen { width: 84px; }
.controles-audio .rango::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 999px;
  background: linear-gradient(to right, var(--relleno) var(--relleno-hasta), var(--cargado) var(--relleno-hasta),
    var(--cargado) var(--cargado-hasta), var(--pista) var(--cargado-hasta));
}
.controles-audio .rango::-moz-range-track {
  height: 4px;
  border-radius: 999px;
  background: linear-gradient(to right, var(--relleno) var(--relleno-hasta), var(--cargado) var(--relleno-hasta),
    var(--cargado) var(--cargado-hasta), var(--pista) var(--cargado-hasta));
}
/* La bolita sale al pasar el ratón o con el foco; en táctil siempre, para ver dónde coger */
.controles-audio .rango::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  margin-top: -5px;
  border: 0;
  border-radius: 999px;
  background: var(--relleno);
  transform: scale(0);
  transition: transform 0.12s;
}
.controles-audio .rango::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border: 0;
  border-radius: 999px;
  background: var(--relleno);
  transform: scale(0);
  transition: transform 0.12s;
}
.controles-audio .rango:hover::-webkit-slider-thumb,
.controles-audio .rango:active::-webkit-slider-thumb,
.controles-audio .rango:focus-visible::-webkit-slider-thumb { transform: scale(1); }
.controles-audio .rango:hover::-moz-range-thumb,
.controles-audio .rango:active::-moz-range-thumb,
.controles-audio .rango:focus-visible::-moz-range-thumb { transform: scale(1); }
@media (pointer: coarse) {
  .controles-audio .rango::-webkit-slider-thumb { transform: scale(1); }
  .controles-audio .rango::-moz-range-thumb { transform: scale(1); }
}
.controles-audio .rango:focus-visible { outline: none; }
.controles-audio .rango:focus-visible::-webkit-slider-runnable-track { outline: 2px solid rgb(255 255 255 / 0.5); outline-offset: 4px; }
.controles-audio .rango:focus-visible::-moz-range-track { outline: 2px solid rgb(255 255 255 / 0.5); outline-offset: 4px; }
.controles-audio.compacto .rango:focus-visible::-webkit-slider-runnable-track { outline-color: var(--p-primary-color); }
.controles-audio.compacto .rango:focus-visible::-moz-range-track { outline-color: var(--p-primary-color); }

.controles-audio .boton { outline: none; }
.controles-audio .boton:focus-visible { box-shadow: 0 0 0 2px #171717, 0 0 0 4px rgb(255 255 255 / 0.6); }
</style>
