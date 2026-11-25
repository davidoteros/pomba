import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import Components from 'unplugin-vue-components/vite';
import {PrimeVueResolver} from '@primevue/auto-import-resolver';
import { viteStaticCopy } from 'vite-plugin-static-copy'


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