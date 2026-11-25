<script setup>
defineProps({
  nombre: { type: String, required: true },
})
</script>

<template>
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" class="block" :class="{ '-scale-x-100': nombre === 'anterior' }">
    <path v-if="nombre === 'play'" d="M7 5.2v13.6a1.2 1.2 0 0 0 1.84 1.02l10.9-6.8a1.2 1.2 0 0 0 0-2.04L8.84 4.18A1.2 1.2 0 0 0 7 5.2z" />
    <template v-else-if="nombre === 'pausa'">
      <rect x="5.5" y="4.5" width="4.5" height="15" rx="1.4" />
      <rect x="14" y="4.5" width="4.5" height="15" rx="1.4" />
    </template>
    <template v-else-if="nombre === 'siguiente' || nombre === 'anterior'">
      <path d="M4.5 6.3v11.4a1.2 1.2 0 0 0 1.86 1l8.6-5.7a1.2 1.2 0 0 0 0-2L6.36 5.3A1.2 1.2 0 0 0 4.5 6.3z" />
      <rect x="16.5" y="5" width="3" height="14" rx="1.5" />
    </template>
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
