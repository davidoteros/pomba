<script setup>
import { ref, watch } from 'vue'
import { useGestorItems } from '@/stores/items'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'

const gestor = useGestorItems()

const inputRenombrar = ref('')
const errorNombre = ref('')
const cajaNombre = ref(null)

// Al abrir, selecciona el nombre sin la extensión
function seleccionarNombre() {
  const caja = cajaNombre.value?.$el
  if (!caja) return
  const punto = inputRenombrar.value.lastIndexOf('.')
  const esArchivo = gestor.modal.payload?.tipo === 'archivo'
  caja.focus()
  caja.setSelectionRange(0, esArchivo && punto > 0 ? punto : inputRenombrar.value.length)
}

watch(() => gestor.modal, (modal) => {
  if (modal.open && modal.name === 'renombrar') {
    inputRenombrar.value = modal.payload?.nombre || ''
    errorNombre.value = ''
  }
}, { deep: true }) //observa cambios en propiedades internas del objeto, no solo si cambia su referencia

async function renombrar() {
  const id = gestor.modal.payload.id
  errorNombre.value = await gestor.renombrarItem(id, inputRenombrar.value) || ''
  if (!errorNombre.value) {
    gestor.cerrarModal()
    inputRenombrar.value = ''
  }
}
</script>

<template>
  <Dialog
    v-if="gestor.modal.name === 'renombrar'"
    v-model:visible="gestor.modal.open"
    header="Renombrar"
    :style="{ width: '25rem' }"
    modal :draggable="false" :closable="false"
    @show="seleccionarNombre"
  >
    <div class="flex flex-col gap-2 mb-4">
      <InputText
        ref="cajaNombre"
        v-model="inputRenombrar"
        class="flex-auto"
        autocomplete="off"
        placeholder="Nuevo nombre"
        maxlength="255"
        :invalid="!!errorNombre"
        @input="errorNombre = ''"
        @keyup.enter="renombrar"
        autofocus
      />
      <Message v-if="errorNombre" severity="error" size="small" variant="simple">{{ errorNombre }}</Message>
    </div>
    <template #footer>
      <Button label="Cancelar" text severity="secondary" @click="gestor.cerrarModal" />
      <Button label="Confirmar" @click="renombrar" :disabled="!inputRenombrar.trim()" />
    </template>
  </Dialog>
</template>
