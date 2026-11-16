import api from './axios';

export const apiUsers = {

  /* Devuelve el perfil del usuario autenticado */
  async obtenerPerfil(config) {
    const { data } = await api.get('user/me/', config);
    return data;
  },

  /* Actualiza nombre, apellidos o tema */
  async actualizarPerfil(datos) {
    const { data } = await api.patch('user/me/', datos);
    return data;
  },

  /* Sube o reemplaza la foto de perfil */
  async subirFotoPerfil(archivo) {
    const datos = new FormData();
    datos.append('foto_perfil', archivo);
    const { data } = await api.post('user/me/foto/', datos, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  /* Cambia el email; pide la contraseña actual */
  async cambiarEmail(emailNuevo, contrasenaActual) {
    const { data } = await api.post('user/me/cambiar-email/', {
      email_nuevo: emailNuevo,
      password_actual: contrasenaActual,
    });
    return data;
  },

  /* Cambia la contraseña del usuario */
  async cambiarContrasena(contrasenaActual, contrasenaNueva) {
    const { data } = await api.post('user/me/cambiar-password/', {
      password_actual: contrasenaActual,
      password_nuevo: contrasenaNueva,
    });
    return data;
  },

  /* Guarda la preferencia de tema claro/oscuro en la BD */
  async guardarTema(tema) {
    await api.patch('user/me/', { tema });
  },

  /* Elimina la cuenta del usuario autenticado; pide la contraseña actual */
  async eliminarCuenta(contrasenaActual) {
    await api.delete('user/me/', { data: { password_actual: contrasenaActual } });
  },
};
