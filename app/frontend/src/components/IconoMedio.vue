<script setup>
defineProps({
  nombre: { type: String, required: true },
})
</script>

<template>
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" class="block">
    <path v-if="nombre === 'play'" d="M7 5.2v13.6a1.2 1.2 0 0 0 1.84 1.02l10.9-6.8a1.2 1.2 0 0 0 0-2.04L8.84 4.18A1.2 1.2 0 0 0 7 5.2z" />
    <template v-else-if="nombre === 'pausa'">
      <rect x="5.5" y="4.5" width="4.5" height="15" rx="1.4" />
      <rect x="14" y="4.5" width="4.5" height="15" rx="1.4" />
    </template>
    <!-- "Anterior" es "siguiente" volteado dentro del dibujo: Safari no voltea bien el SVG con CSS -->
    <g v-else-if="nombre === 'siguiente' || nombre === 'anterior'" :transform="nombre === 'anterior' ? 'matrix(-1 0 0 1 24 0)' : undefined">
      <path d="M4.5 6.3v11.4a1.2 1.2 0 0 0 1.86 1l8.6-5.7a1.2 1.2 0 0 0 0-2L6.36 5.3A1.2 1.2 0 0 0 4.5 6.3z" />
      <rect x="16.5" y="5" width="3" height="14" rx="1.5" />
    </g>
    <g v-else-if="nombre === 'pantalla-completa' || nombre === 'salir-completa' || nombre === 'otra-vez'"
       fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
      <path v-if="nombre === 'pantalla-completa'" d="M4 9V5.5A1.5 1.5 0 0 1 5.5 4H9M15 4h3.5A1.5 1.5 0 0 1 20 5.5V9M20 15v3.5a1.5 1.5 0 0 1-1.5 1.5H15M9 20H5.5A1.5 1.5 0 0 1 4 18.5V15" />
      <path v-else-if="nombre === 'salir-completa'" d="M9 4v3.5A1.5 1.5 0 0 1 7.5 9H4M20 9h-3.5A1.5 1.5 0 0 1 15 7.5V4M15 20v-3.5a1.5 1.5 0 0 1 1.5-1.5H20M4 15h3.5A1.5 1.5 0 0 1 9 16.5V20" />
      <path v-else d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4.5h4.5" />
    </g>
    <template v-else>
      <path d="M3 9.6v4.8A1.6 1.6 0 0 0 4.6 16H7l4.2 3.6c.75.64 1.8.1 1.8-.86V5.26c0-.96-1.05-1.5-1.8-.86L7 8H4.6A1.6 1.6 0 0 0 3 9.6z" />
      <g fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <path v-if="nombre === 'silencio'" d="M16 9.5l5 5m0-5l-5 5" />
        <path v-else d="M15.5 9.2a4 4 0 0 1 0 5.6" />
        <path v-if="nombre === 'volumen-alto'" d="M18.2 6.6a7.6 7.6 0 0 1 0 10.8" />
      </g>
    </template>
  </svg>
</template>
