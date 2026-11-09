import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import Login from './views/Login.vue'
import Home from './views/Home.vue'
import Register from './views/Register.vue'
import AppLayout from './layout/AppLayout.vue'
import SearchResults from './views/SearchResults.vue'


const routes = [
  // --- Autenticación ---
  { path: '/', component: Login },
  { path: '/register', component: Register },

  // --- App General ---
  {
      path: '/home',
      component: AppLayout,
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          redirect: { name: 'home', params: { view: 'drive' } }
        },
        {
          path: ':view/:folderId?',
          name: 'home',
          component: Home
        },
        {
          path: 'search',
          name: 'search',
          component: SearchResults,
        },
      ]
    },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})


router.beforeEach(async (to) => {
  const userStore = useUserStore()

  // La primera vez se pregunta a Django si hay sesión
  if (!userStore.sesionComprobada) {
    await userStore.comprobarSesion()
  }

  const loggedIn = userStore.autenticado

  const isAuthRoute = to.meta.requiresAuth

  // No logueado intentando entrar a zona privada
  if (isAuthRoute && !loggedIn) {
    return '/'
  }

  // Logueado intentando ir a login/register
  if (loggedIn && (to.path === '/' || to.path === '/register')) {
    return '/home'
  }
})

export default router