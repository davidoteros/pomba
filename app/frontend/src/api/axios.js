import axios from 'axios';
import router from '@/router'
import { useUserStore } from '@/stores/user'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/';

// Axios copia la cookie csrftoken en la cabecera X-CSRFToken (solo a nuestro origen)
const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
});

// Sesión caducada: vuelta al login. Las de comprobarSesion las decide el guard del router
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const codigo = error.response?.data?.errors?.[0]?.code;

    if (codigo === 'not_authenticated' && !error.config?.comprobarSesion) {
      useUserStore().olvidarSesion();
      router.push('/');
    }

    return Promise.reject(error);
  }
);


export default api;