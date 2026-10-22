<script setup>
import { computed } from 'vue'
import { useGestorItems } from '@/stores/items'
import Dialog from 'primevue/dialog'

const gestor = useGestorItems()

const tipoPreview = computed(() => gestor.modal.payload?.item?.tipo_visor || null)
</script>

<template>
  <Dialog
    v-if="gestor.modal.name === 'previsualizar'"
    v-model:visible="gestor.modal.open"
    :style="tipoPreview === 'audio' ? { width: '26rem' } : { width: '92vw', maxWidth: '1200px' }"
    :breakpoints="{ '640px': '96vw' }"
    modal :draggable="false" :closable="false"
    @hide="gestor.cerrarModal"
    :pt="{
      root:    { class: 'overflow-hidden !rounded-2xl shadow-2xl' },
      header:  { class: '!hidden' },
      content: { style: 'padding:0; overflow:hidden' },
    }"
  >
    <!-- IMAGEN -->
    <div v-if="tipoPreview === 'imagen'" class="relative bg-black select-none">
      <div class="absolute inset-x-0 top-0 z-10 flex items-center justify-between px-4 py-3">
        <div class="flex items-center gap-2 min-w-0 bg-black/40 backdrop-blur-sm rounded-full px-3 py-1">
          <i class="pi pi-image text-white/60 text-xs shrink-0" />
          <span class="text-white/90 text-sm font-medium truncate max-w-xs">
            {{ gestor.modal.payload?.item?.nombre }}
          </span>
        </div>
      </div>
      <button
        @click="gestor.cerrarModal"
        class="absolute top-3 right-3 z-20 w-8 h-8 rounded-full bg-black/40 hover:bg-black/70
              flex items-center justify-center text-white transition-colors cursor-pointer"
        aria-label="Cerrar"
      >
        <i class="pi pi-times text-xs" />
      </button>
      <img
        :src="gestor.modal.payload?.url"
        :alt="gestor.modal.payload?.item?.nombre"
        class="block mx-auto max-w-full object-contain"
        style="max-height: 90vh"
      />
    </div>

    <!-- AUDIO -->
    <div v-else-if="tipoPreview === 'audio'" class="flex flex-col bg-surface-0 dark:bg-surface-900">
      <div class="flex items-center justify-between px-5 py-4">
        <div class="flex items-center gap-2 min-w-0">
          <i class="pi pi-headphones text-pink-400 shrink-0" />
          <span class="text-surface-800 dark:text-surface-100 text-sm font-semibold truncate">
            {{ gestor.modal.payload?.item?.nombre }}
          </span>
        </div>
        <button
          @click="gestor.cerrarModal"
          class="w-7 h-7 shrink-0 rounded-full
                bg-surface-100 hover:bg-surface-200
                dark:bg-surface-700 dark:hover:bg-surface-600
                flex items-center justify-center
                text-surface-500 dark:text-surface-400
                transition-colors cursor-pointer ml-2"
          aria-label="Cerrar"
        >
          <i class="pi pi-times text-xs" />
        </button>
      </div>
      <div class="px-5 py-6">
        <audio controls autoplay :src="gestor.modal.payload?.url" class="w-full" />
      </div>
    </div>

    <!-- VIDEO -->
    <div v-else-if="tipoPreview === 'video'" class="relative bg-black">
      <div class="absolute inset-x-0 top-0 z-10 flex items-center justify-between px-4 py-3">
        <div class="flex items-center gap-2 min-w-0 bg-black/40 backdrop-blur-sm rounded-full px-3 py-1">
          <i class="pi pi-video text-white/60 text-xs shrink-0" />
          <span class="text-white/90 text-sm font-medium truncate max-w-xs">
            {{ gestor.modal.payload?.item?.nombre }}
          </span>
        </div>
      </div>
      <button
        @click="gestor.cerrarModal"
        class="absolute top-3 right-3 z-20 w-8 h-8 rounded-full bg-black/40 hover:bg-black/70
              flex items-center justify-center text-white transition-colors cursor-pointer"
        aria-label="Cerrar"
      >
        <i class="pi pi-times text-xs" />
      </button>
      <video
        controls autoplay
        :src="gestor.modal.payload?.url"
        class="block mx-auto max-w-full"
        style="max-height: 90vh; padding-top: 3rem"
      />
    </div>

    <!-- PDF -->
    <div v-else-if="tipoPreview === 'pdf'" class="flex flex-col">
      <div class="flex items-center justify-between px-4 py-3
                  bg-surface-100 dark:bg-surface-800
                  border-b border-surface-200 dark:border-surface-700">
        <div class="flex items-center gap-2 min-w-0">
          <i class="pi pi-file-pdf text-red-400 shrink-0" />
          <span class="text-surface-700 dark:text-surface-200 text-sm font-medium truncate">
            {{ gestor.modal.payload?.item?.nombre }}
          </span>
        </div>
        <button
          @click="gestor.cerrarModal"
          class="w-7 h-7 shrink-0 rounded-full bg-surface-200 dark:bg-surface-700
                hover:bg-surface-300 dark:hover:bg-surface-600
                flex items-center justify-center text-surface-500 dark:text-surface-400
                transition-colors cursor-pointer ml-2"
          aria-label="Cerrar"
        >
          <i class="pi pi-times text-xs" />
        </button>
      </div>
      <iframe
        :src="gestor.modal.payload?.url"
        class="w-full block border-0"
        style="height: 87vh"
      />
    </div>
  </Dialog>
</template>
