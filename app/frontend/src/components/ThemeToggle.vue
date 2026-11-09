<script setup>
import { ref, onMounted } from "vue";
import Button from "primevue/button";
import { apiUsers } from "@/api/users";
import { useUserStore } from "@/stores/user";

const userStore = useUserStore();
const isDark = ref(false);

const applyTheme = (dark) => {
  document.documentElement.classList.toggle("dark", dark);
  localStorage.setItem("theme", dark ? "oscuro" : "claro");
};

const toggleDark = async () => {
  isDark.value = !isDark.value;
  applyTheme(isDark.value);
  if (userStore.autenticado) {
    await apiUsers.guardarTema(isDark.value ? "oscuro" : "claro");
  }
};

onMounted(() => {
  const saved = localStorage.getItem("theme");
  if (saved === "oscuro" || saved === "dark") {
    isDark.value = true;
    applyTheme(true);
  }
});
</script>

<template>
<Button
  :icon="isDark ? 'pi pi-moon' : 'pi pi-sun'"
  rounded
  text
  class="hover:bg-primary/10 dark:hover:bg-primary/20 transition-colors duration-300"
  @click="toggleDark"
/>
</template>
