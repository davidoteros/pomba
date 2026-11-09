import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { apiUsers } from '@/api/users'
import { authService } from '@/api/auth'

const PERFIL_VACIO = { nombre: '', apellidos: '', email: '', foto_perfil_url: null }

export const useUserStore = defineStore('user', () => {
  const perfil = ref({ ...PERFIL_VACIO })

  // La cookie de sesión es HttpOnly: hay que preguntar a Django
  const autenticado = ref(false)
  const sesionComprobada = ref(false)

  const inicial = computed(() =>
    perfil.value.nombre ? perfil.value.nombre.charAt(0).toUpperCase() : null
  )

  function aplicarPerfil(datos) {
    perfil.value = { ...datos }
    if (datos.tema) {
      const dark = datos.tema === 'oscuro'
      document.documentElement.classList.toggle('dark', dark)
      localStorage.setItem('theme', datos.tema)
    }
  }

  // Cualquier fallo de /me/ cuenta como no autenticado
  async function comprobarSesion() {
    try {
      aplicarPerfil(await apiUsers.obtenerPerfil({ comprobarSesion: true }))
      autenticado.value = true
    } catch {
      autenticado.value = false
    } finally {
      sesionComprobada.value = true
    }
  }

  async function iniciarSesion(email, password) {
    aplicarPerfil(await authService.login(email, password))
    autenticado.value = true
    sesionComprobada.value = true
  }

  // Se olvida aunque el servidor no responda
  async function cerrarSesion() {
    try {
      await authService.logout()
    } catch (error) {
      console.error('No se pudo cerrar la sesión en el servidor', error)
    } finally {
      olvidarSesion()
    }
  }

  // Solo limpia el navegador
  function olvidarSesion() {
    autenticado.value = false
    sesionComprobada.value = true
    perfil.value = { ...PERFIL_VACIO }
  }

  //Lo utilizamos para guardar localmente sin tener que recargar la página entera 
  function actualizarPerfil(datos) {
    perfil.value = { ...perfil.value, ...datos }
  }

  return {
    perfil, inicial, autenticado, sesionComprobada,
    comprobarSesion, iniciarSesion, cerrarSesion, olvidarSesion, actualizarPerfil,
  }
})
