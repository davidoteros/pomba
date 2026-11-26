// Lo común de los reproductores de audio y vídeo: el navegador descarga y reproduce, aquí solo el estado y las acciones
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

export function formatoTiempo(s) {
  if (!Number.isFinite(s) || s < 0) s = 0
  s = Math.floor(s)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const seg = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${seg}` : `${m}:${seg}`
}

// medio: ref al <audio>/<video>; src y pista: getters. Si cambia solo src (enlace renovado), se sigue por donde iba
export function useMedio(medio, { src, pista }) {
  const pausado = ref(true)
  const terminado = ref(false)
  const cargando = ref(false)
  const tiempo = ref(0)
  const duracion = ref(0)
  const cargado = ref(0)
  const volumen = ref(1)
  const silenciado = ref(false)
  const arrastre = ref(null) // posición mientras se arrastra la barra, sin mover aún el medio

  // Otro archivo: se para el anterior mientras llega su enlace y la barra vuelve a cero
  watch(pista, () => {
    medio.value?.pause()
    tiempo.value = 0
    duracion.value = 0
    cargado.value = 0
    terminado.value = false
  })

  // Enlace nuevo: si es de otro archivo empieza desde el principio; si es el mismo (renovado), por donde iba
  let pistaDelEnlace = null
  let reanudarEn = null
  function alLlegarEnlace(url) {
    if (!url) return
    const misma = pistaDelEnlace === pista()
    reanudarEn = misma ? tiempo.value : null
    pistaDelEnlace = pista()
    if (!misma || !pausado.value) medio.value.play().catch(() => {})
  }
  // 'post': cuando el elemento ya tiene el src nuevo; el primero, al montarse (antes no existe)
  watch(src, alLlegarEnlace, { flush: 'post' })
  onMounted(() => alLlegarEnlace(src()))

  // Al cerrar, cortar también la descarga (quitar el elemento de la página no la para)
  onBeforeUnmount(() => {
    const m = medio.value
    if (!m) return
    m.pause()
    m.removeAttribute('src')
    m.load()
  })

  // Los eventos usan e.target: al cerrar, el elemento aún avisa cuando la referencia ya es null
  function alAvanzar(e) {
    const m = e.target
    tiempo.value = m.currentTime
    if (m.buffered.length) cargado.value = m.buffered.end(m.buffered.length - 1)
  }

  const eventos = {
    loadedmetadata: (e) => {
      duracion.value = e.target.duration || 0
      if (reanudarEn !== null) e.target.currentTime = reanudarEn
      reanudarEn = null
    },
    durationchange: (e) => { duracion.value = e.target.duration || 0 },
    timeupdate: alAvanzar,
    progress: alAvanzar,
    play: () => { pausado.value = false; terminado.value = false },
    pause: () => { pausado.value = true },
    ended: () => { terminado.value = true },
    waiting: () => { cargando.value = true },
    loadstart: () => { cargando.value = !!src() },
    canplay: () => { cargando.value = false },
    playing: () => { cargando.value = false },
    volumechange: (e) => {
      volumen.value = e.target.volume
      silenciado.value = e.target.muted
    },
  }

  const posicion = computed(() => arrastre.value ?? tiempo.value)
  const pct = (s) => (duracion.value ? `${Math.min((s / duracion.value) * 100, 100)}%` : '0%')
  const nivel = computed(() => (silenciado.value ? 0 : volumen.value))
  const iconoVolumen = computed(() => (nivel.value === 0 ? 'silencio' : nivel.value < 0.5 ? 'volumen-bajo' : 'volumen-alto'))

  function alternar() {
    const m = medio.value
    if (!m?.src) return
    if (m.paused) m.play().catch(() => {})
    else m.pause()
  }

  function irA(segundos) {
    if (duracion.value) medio.value.currentTime = Math.min(Math.max(segundos, 0), duracion.value)
  }

  const saltar = (segundos) => irA(medio.value.currentTime + segundos)

  function silenciar() {
    const m = medio.value
    m.muted = !m.muted
    if (!m.muted && m.volume === 0) m.volume = 1
  }

  function alMoverVolumen(e) {
    const v = Number(e.target.value)
    medio.value.volume = v
    medio.value.muted = v === 0
  }

  function alSoltarBarra(e) {
    irA(Number(e.target.value))
    arrastre.value = null
  }

  return {
    pausado, terminado, cargando, tiempo, duracion, cargado, silenciado, arrastre, posicion, nivel, iconoVolumen, eventos,
    pct, alternar, irA, saltar, silenciar, alMoverVolumen, alSoltarBarra,
  }
}
