// Piezas comunes de los visores a pantalla completa (fotos, PDF, audio y vídeo)
import { computed, onMounted, reactive, ref } from 'vue'
import { apiItems } from '@/api/items'
import { mensajeDeAccion } from '@/utils/errors'

// Los archivos de la carpeta: el que se ve, anterior / siguiente y el "2 / 5"
export function useListaVisor(lista, inicio = 0) {
  const indice = ref(inicio)
  const actual = computed(() => lista()[indice.value])
  const hayAnterior = computed(() => indice.value > 0)
  const haySiguiente = computed(() => indice.value < lista().length - 1)
  const contador = computed(() => (lista().length > 1 ? `${indice.value + 1} / ${lista().length}` : ''))
  const anterior = () => { if (hayAnterior.value) indice.value-- }
  const siguiente = () => { if (haySiguiente.value) indice.value++ }
  return { indice, actual, hayAnterior, haySiguiente, contador, anterior, siguiente }
}

// id -> { url, error, reintentada }; el enlace firmado de cada archivo se pide al llegar a él
export function useEnlacesFirmados(mensajeError) {
  const enlaces = reactive({})

  async function pedir(item, reintentada = false) {
    if (!item || (enlaces[item.id] && !reintentada)) return
    enlaces[item.id] = { url: enlaces[item.id]?.url ?? null, error: null, reintentada }
    try {
      enlaces[item.id].url = (await apiItems.previsualizar(item.id)).url
    } catch (e) {
      enlaces[item.id].error = mensajeDeAccion(e, mensajeError)
    }
  }

  // Caducan a los 5 min: si falla se pide otro una vez; false si ya se había reintentado
  async function reintentar(item) {
    if (enlaces[item.id]?.reintentada) return false
    await pedir(item, true)
    return true
  }

  return { enlaces, pedir, reintentar }
}

// Clic en el fondo cierra: pulsar y soltar ahí sin moverse (no al arrastrar, hacer scroll ni seleccionar)
export function useCerrarEnFondo(esFondo, cerrar) {
  let inicio = null
  const alPulsar = (e) => { inicio = esFondo(e) ? { x: e.clientX, y: e.clientY } : null }
  function alSoltar(e) {
    if (inicio && esFondo(e) && Math.hypot(e.clientX - inicio.x, e.clientY - inicio.y) < 6) cerrar()
    inicio = null
  }
  return { alPulsar, alSoltar }
}

// El foco entra en el visor al abrirse (si no, se queda en la tabla de detrás); el elemento necesita tabindex="-1"
export function useFocoAlAbrir(elemento = ref(null)) {
  onMounted(() => elemento.value?.focus())
  return elemento
}
