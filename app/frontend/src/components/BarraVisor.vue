<script setup>
// Barra negra fina de los visores a pantalla completa (PDF e imágenes); en el hueco, lo de cada visor
defineProps({
  nombre: { type: String, required: true },
  icono: { type: String, required: true },
})
const emit = defineEmits(['descargar', 'cerrar'])
</script>

<template>
  <div class="h-12 shrink-0 flex items-center gap-1 pl-4 pr-2 bg-neutral-950 text-neutral-100">
    <div class="flex items-center gap-2 min-w-0 flex-1">
      <i :class="['pi shrink-0', icono]" />
      <span class="text-sm font-medium truncate">{{ nombre }}</span>
    </div>

    <slot />

    <span class="w-px h-5 bg-neutral-700 mx-1" />
    <button
      @click="emit('descargar')"
      class="w-9 h-9 rounded-full flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer"
      title="Descargar" aria-label="Descargar"
    >
      <i class="pi pi-download" />
    </button>
    <button
      @click="emit('cerrar')"
      class="w-9 h-9 rounded-full flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer"
      title="Cerrar" aria-label="Cerrar"
    >
      <i class="pi pi-times" />
    </button>
  </div>
</template>
