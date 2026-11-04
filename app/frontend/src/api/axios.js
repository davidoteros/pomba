import axios from 'axios';
import router from '@/router'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/';

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

const publicRoutes = [
  'auth/obtain_token/',
  'auth/refresh_token/',
  'user/register/'
]

// 1. INTERCEPTOR DE PETICIÓN: Añadir el token automáticamente
api.interceptors.request.use((config) => {
  // Comprobamos si la URL actual coincide con alguna ruta pública
  const isPublic = publicRoutes.some(route => config.url?.includes(route));

  if (!isPublic) {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }

  return config;
});


// 2. INTERCEPTOR DE RESPUESTA: Manejar el refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const url = originalRequest.url || '';

    //Si es publica no queremos que reintente nada
    const isPublic = publicRoutes.some(route => url.includes(route));

    // Si es 401 y no es un reintento
    if (error.response?.status === 401 && !originalRequest._retry && !isPublic) {
      originalRequest._retry = true;

      try {
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) throw new Error("No hay refresh token");

        // Usamos una instancia limpia de axios para evitar bucles infinitos si esta petición también falla
        const { data } = await axios.post(`${BASE_URL}auth/refresh_token/`, {
          refresh: refreshToken
        });

        localStorage.setItem('access_token', data.access);
        
        // Reintentamos la petición original con el nuevo token
        originalRequest.headers['Authorization'] = `Bearer ${data.access}`;
        return api(originalRequest);

      } catch (refreshError) {
        console.error("Sesión expirada. Redirigiendo...");
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        router.push('/'); 
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);


export default api;