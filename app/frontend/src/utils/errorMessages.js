export const errorMessages = {
  fields: {
    email: {
      unique  : "Este email ya se encuentra en uso",
      invalid : "El formato del correo no es válido",
      required: "El correo es obligatorio",
    },
    password: {
      required: "La contraseña es obligatoria",
    },
  },

  codes: {
    no_active_account: "El correo o la contraseña no son correctos",
    required: "Este campo es obligatorio",
    unique: "Este valor ya está en uso",
    not_authenticated: "Tu sesión ha caducado. Vuelve a iniciar sesión.",
  },

  fallback: "Ha ocurrido un error inesperado",
  network : "No se pudo conectar con el servidor",
};