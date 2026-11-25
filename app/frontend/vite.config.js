import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import Components from 'unplugin-vue-components/vite';
import {PrimeVueResolver} from '@primevue/auto-import-resolver';
import { viteStaticCopy } from 'vite-plugin-static-copy'
import { readFileSync } from 'fs'

// Solo en la demo: la tarjeta que sale al pegar el enlace en LinkedIn, WhatsApp o un correo (Open Graph)
const URL_DEMO = 'https://davidoteros.github.io/pomba/'
const TITULO_DEMO = 'Pomba - demo de una nube privada para tu casa'
const DESCRIPCION_DEMO = 'Sube, ordena y previsualiza archivos como en Drive. Todo se queda en tu navegador: no hace falta cuenta.'

function tarjetaDemo() {
  const meta = (attrs) => ({ tag: 'meta', attrs, injectTo: 'head' })
  return {
    name: 'pomba-tarjeta-demo',
    transformIndexHtml: (html) => ({
      html: html.replace('<title>Pomba</title>', `<title>${TITULO_DEMO}</title>`),
      tags: [
        meta({ property: 'og:type', content: 'website' }),
        meta({ property: 'og:url', content: URL_DEMO }),
        meta({ property: 'og:title', content: TITULO_DEMO }),
        meta({ property: 'og:description', content: DESCRIPCION_DEMO }),
        meta({ property: 'og:image', content: `${URL_DEMO}tarjeta.png` }),
        meta({ property: 'og:image:width', content: '2400' }),
        meta({ property: 'og:image:height', content: '1260' }),
        meta({ property: 'og:locale', content: 'es_ES' }),
        meta({ name: 'twitter:card', content: 'summary_large_image' }),
      ],
    }),
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'tarjeta.png', source: readFileSync(path.resolve(__dirname, 'src/demo/tarjeta.png')) })
    },
  }
}


export default defineConfig(({ mode }) => ({
  // La demo de GitHub Pages vive en /pomba/
  base: mode === 'demo' ? '/pomba/' : '/',
  plugins: [
    vue(),
    tailwindcss(),
    Components({
      resolvers: [
        PrimeVueResolver()
      ]
    }),
    viteStaticCopy({
      targets: [{
        src: ['cmaps', 'standard_fonts', 'iccs', 'wasm'].map((d) => `node_modules/pdfjs-dist/${d}/*`),
        dest: 'pdfjs',
        rename: { stripBase: 2 },
      }],
    }),
    mode === 'demo' && tarjetaDemo(),
  ],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    watch: {
      usePolling: true,
      interval: 100  
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  }
}))