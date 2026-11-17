<script setup>
import { computed, onMounted } from 'vue'
import ProgressBar from 'primevue/progressbar'
import { useGestorItems } from '@/stores/items'
import { formatBytes } from '@/utils/bytes'

// 'lateral': completa en pantalla ancha y solo un anillo en la barra estrecha; 'completa': siempre entera
const props = defineProps({ variante: { type: String, default: 'completa' } })

const gestor = useGestorItems()

// Al montarse lo pide de nuevo: así el modal del móvil abre con la cifra al día
onMounted(() => gestor.cargarEspacio())

const espacio = computed(() => gestor.espacio)
const porcentaje = computed(() => {
  const { ocupado, cuota } = espacio.value
  return cuota > 0 ? Math.min(100, Math.round((ocupado / cuota) * 100)) : 100
})
// En rojo desde el 80 %
const casiLleno = computed(() => porcentaje.value > 80)
const color = computed(() => (casiLleno.value ? 'var(--p-red-500)' : 'var(--p-primary-color)'))
const texto = computed(() => `${formatBytes(espacio.value.ocupado)} de ${formatBytes(espacio.value.cuota)} usados`)
</script>

<template>
  <div v-if="espacio" :title="`${texto} (${porcentaje} %)`" class="w-full">
    <!-- Anillo: solo en la barra lateral estrecha (tablet) -->
    <div v-if="props.variante === 'lateral'" class="hidden sm:flex lg:hidden justify-center py-2">
      <div
        class="w-7 h-7 rounded-full flex items-center justify-center"
        :style="{ background: `conic-gradient(${color} ${porcentaje}%, var(--p-surface-200) 0)` }"
      >
        <div class="w-5 h-5 rounded-full bg-surface-50 dark:bg-surface-950 flex items-center justify-center">
          <i class="pi pi-cloud text-surface-500" style="font-size: 10px" />
        </div>
      </div>
    </div>

    <!-- Barra con texto -->
    <div :class="props.variante === 'lateral' ? 'hidden lg:block px-3 pt-3 pb-1' : ''">
      <div class="flex items-center gap-3 text-sm font-medium text-surface-700 dark:text-surface-200 mb-2">
        <i class="pi pi-cloud text-base" /> Almacenamiento
      </div>
      <ProgressBar
        :value="porcentaje"
        :show-value="false"
        style="height: 6px"
        :pt="{ value: { style: { background: color } } }"
      />
      <p class="text-xs mt-1.5" :class="casiLleno ? 'text-red-500' : 'text-surface-500 dark:text-surface-400'">
        {{ texto }}
      </p>
    </div>
  </div>
</template>
