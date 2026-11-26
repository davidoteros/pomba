<script setup>
import { computed, defineAsyncComponent } from 'vue'
import { useGestorItems } from '@/stores/items'
import Dialog from 'primevue/dialog'

const VisorPdf = defineAsyncComponent(() => import('@/components/VisorPdf.vue'))
const VisorImagen = defineAsyncComponent(() => import('@/components/VisorImagen.vue'))
const VisorAudio = defineAsyncComponent(() => import('@/components/VisorAudio.vue'))
const VisorVideo = defineAsyncComponent(() => import('@/components/VisorVideo.vue'))

const gestor = useGestorItems()

const tipoPreview = computed(() => gestor.modal.payload?.item?.tipo_visor || null)

// Todos los visores ocupan toda la pantalla
const pantallaCompleta = computed(() => ['pdf', 'imagen', 'audio', 'video'].includes(tipoPreview.value))

const estiloVentana = computed(() => {
  if (pantallaCompleta.value) return { width: '100vw', height: '100dvh', maxHeight: '100dvh', margin: 0 }
  return { width: '92vw', maxWidth: '1200px' }
})
</script>

<template>
  <Dialog
    v-if="gestor.modal.name === 'previsualizar'"
    v-model:visible="gestor.modal.open"
    :style="estiloVentana"
    :breakpoints="pantallaCompleta ? {} : { '640px': '96vw' }"
    modal :draggable="false" :closable="false"
    @hide="gestor.cerrarModal"
    :pt="{
      root:    { class: pantallaCompleta ? 'overflow-hidden !rounded-none !border-0' : 'overflow-hidden !rounded-2xl shadow-2xl' },
      header:  { class: '!hidden' },
      content: { style: 'padding:0; overflow:hidden' },
    }"
  >
    <!-- IMAGEN -->
    <VisorImagen
      v-if="tipoPreview === 'imagen'"
      :imagenes="gestor.modal.payload.imagenes"
      :inicio="gestor.modal.payload.inicio"
      @cerrar="gestor.cerrarModal"
      @descargar="gestor.descargarArchivo"
    />

    <!-- AUDIO -->
    <VisorAudio
      v-else-if="tipoPreview === 'audio'"
      :pistas="gestor.modal.payload.pistas"
      :inicio="gestor.modal.payload.inicio"
      :portadas="gestor.modal.payload.portadas"
      :carpeta="gestor.modal.payload.carpeta"
      @cerrar="gestor.cerrarModal"
      @descargar="gestor.descargarArchivo"
    />

    <!-- VIDEO -->
    <VisorVideo
      v-else-if="tipoPreview === 'video'"
      :videos="gestor.modal.payload.videos"
      :inicio="gestor.modal.payload.inicio"
      @cerrar="gestor.cerrarModal"
      @descargar="gestor.descargarArchivo"
    />

    <!-- PDF -->
    <VisorPdf
      v-else-if="tipoPreview === 'pdf'"
      :url="gestor.modal.payload?.url"
      :nombre="gestor.modal.payload?.item?.nombre"
      @cerrar="gestor.cerrarModal"
      @descargar="gestor.descargarArchivo(gestor.modal.payload.item)"
    />
  </Dialog>
</template>
