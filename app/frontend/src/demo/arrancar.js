// Arranque de la demo de GitHub Pages: backend falso en el navegador y sin pantalla de login
import { setupWorker } from 'msw/browser'
import router from '@/router'
import { useUserStore } from '@/stores/user'
import { respuestas } from './respuestas.js'
import { reiniciar } from './datos.js'

// Pastilla "DEMO" junto al logo; solo desde 1024 px, que es cuando se ve el nombre Pomba
function ponerAviso() {
  const estilo = document.createElement('style')
  estilo.textContent = `
    #aviso-demo { position: fixed; top: 34px; left: 168px; z-index: 50; padding: 2px 8px; border-radius: 6px;
      font: 700 11px/1.4 system-ui, sans-serif; letter-spacing: .05em; background: #eef2ff; color: #4f46e5; cursor: default }
    html.dark #aviso-demo { background: rgba(99, 102, 241, .2); color: #a5b4fc }
    @media (max-width: 1023px) { #aviso-demo { display: none } }`
  const aviso = document.createElement('div')
  aviso.id = 'aviso-demo'
  aviso.textContent = 'DEMO'
  aviso.title = 'Demo: nada se guarda. Al recargar vuelve al principio.'
  document.head.appendChild(estilo)
  document.body.appendChild(aviso)
}

export async function arrancarDemo() {
  reiniciar()
  ponerAviso()
  await setupWorker(...respuestas).start({
    serviceWorker: { url: `${import.meta.env.BASE_URL}mockServiceWorker.js` },
    onUnhandledRequest: 'bypass',
    quiet: true,
  })

  // Login, registro y "Cerrar sesión" vuelven a empezar la demo dentro de la cuenta de ejemplo
  router.beforeEach((to) => {
    if (to.path === '/' || to.path === '/register') {
      reiniciar()
      useUserStore().sesionComprobada = false
      return '/home'
    }
  })
}
