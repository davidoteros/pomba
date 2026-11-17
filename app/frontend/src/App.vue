<template>
  <div>
    <router-view />
  </div>
</template>

<script setup>
// Un fichero soltado fuera de la zona de subida no debe abrirse en la pestaña (sacaría de Pomba)
function noAbrirFichero(event) {
  if (event.defaultPrevented || !event.dataTransfer?.types.includes('Files')) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'none'
}

window.addEventListener('dragover', noAbrirFichero)
window.addEventListener('drop', noAbrirFichero)
</script>