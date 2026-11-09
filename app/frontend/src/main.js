import { createApp } from 'vue'
import {createPinia} from 'pinia'
import './style.css'
import App from './App.vue'
import router from './router.js'
import { authService } from './api/auth'

import PrimeVue from 'primevue/config'
import Aura from '@primeuix/themes/aura'
import { definePreset } from '@primeuix/themes'
import 'primeicons/primeicons.css'

const pinia = createPinia()
const app = createApp(App)


// Paleta Clara
const slateSurface = {
    0:   '#ffffff',
    50:  '#f8fafc',
    100: '#f1f5f9',
    150: '#e8edf4',
    200: '#e2e8f0',
    300: '#cbd5e1',
    400: '#94a3b8',
    500: '#64748b',
    600: '#475569',
    700: '#334155',
    800: '#1e293b',
    900: '#0f172a',
    950: '#020617',
};

// Paleta Oscura
const slateDarkSurface = {
    0:   '#ffffff',
    50:  '#f8fafc',
    100: '#f1f5f9',
    150: '#e8edf4',
    200: '#e2e8f0',
    300: '#cbd5e1',
    400: '#94a3b8',
    500: '#64748b',
    600: '#475569',
    700: '#334155',
    800: '#2e3d58',
    900: '#29364f',
    950: '#222d42',
};

const MyCustomPreset = definePreset(Aura, {
    semantic: {
        primary: {
            50:  '{indigo.50}',
            100: '{indigo.100}',
            200: '{indigo.200}',
            300: '{indigo.300}',
            400: '{indigo.400}',
            500: '{indigo.500}',
            600: '{indigo.600}',
            700: '{indigo.700}',
            800: '{indigo.800}',
            900: '{indigo.900}',
            950: '{indigo.950}',
        },
        colorScheme: {
            light: {
                surface: slateSurface
            },
            dark: {
                surface: slateDarkSurface
            }
        }
    }
});

app.use(PrimeVue, {
    theme: {
        preset: MyCustomPreset,
        options: {
            darkModeSelector: '.dark',
            cssLayer: {
                name: 'primevue',
                order: 'theme, base, primevue, utilities'
            }
        }
    }
});
app.use(pinia)
app.use(router)

// csrftoken antes del primer POST; si el backend falla, se monta igual
authService.obtenerCsrf()
    .catch(() => {})
    .finally(() => app.mount('#app'))