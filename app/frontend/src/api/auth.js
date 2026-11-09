import api from './axios';

export const authService = {

    // Cookie csrftoken, necesaria antes del primer POST
    async obtenerCsrf() {
        await api.get('auth/csrf/');
    },

    // Devuelve el perfil
    async login(email, password) {
        const { data } = await api.post('auth/login/', { email, password });
        return data;
    },

    async register(email, password, nombre, apellidos) {
        const response = await api.post('user/register/', {email, password, nombre, apellidos})
        return response
    },

    async logout() {
        await api.post('auth/logout/');
    },
};

