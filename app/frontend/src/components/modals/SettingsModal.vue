<template>
  <Dialog
    v-model:visible="visible"
    modal
    position="top"
    :style="{ width: '560px', marginTop: '5vh' }"
    :breakpoints="{ '640px': '95vw' }"
    :draggable="false"
    class="settings-dialog"
  >
    <template #header>
      <span class="font-semibold text-lg">Configuración de cuenta</span>
    </template>

    <!-- PESTAÑAS DE NAVEGACIÓN -->
    <div class="flex gap-1 mb-6 border-b border-surface-200 dark:border-surface-700 pb-0">
      <button
        v-for="pestana in pestanas"
        :key="pestana.clave"
        @click="tabActiva = pestana.clave"
        class="px-4 py-2 text-sm rounded-t-lg transition-colors duration-150"
        :class="tabActiva === pestana.clave
          ? 'border-b-2 border-primary text-primary font-medium'
          : 'text-surface-600 dark:text-surface-400 hover:text-surface-900 dark:hover:text-surface-100'"
      >
        <i :class="pestana.icono" class="mr-2 text-xs" />{{ pestana.etiqueta }}
      </button>
    </div>

    <!-- PESTAÑA: FOTO DE PERFIL -->
    <div v-show="tabActiva === 'foto'" class="flex flex-col items-center gap-5 py-4">
      <div class="relative group cursor-pointer" @click="abrirSelector">
        <div class="w-32 h-32 rounded-full overflow-hidden border-2 border-surface-200 dark:border-surface-700 bg-surface-100 dark:bg-surface-800 flex items-center justify-center">
          <img
            v-if="urlPrevia || userStore.perfil.foto_perfil_url"
            :src="urlPrevia || userStore.perfil.foto_perfil_url"
            alt="Avatar"
            class="w-full h-full object-cover"
          />
          <i v-else class="pi pi-user text-6xl text-surface-400" />
        </div>
        <div class="absolute inset-0 rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
          <i class="pi pi-camera text-white text-2xl" />
        </div>
      </div>

      <input
        ref="inputArchivo"
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        class="hidden"
        @change="alSeleccionarArchivo"
      />

      <div v-if="archivoSeleccionado" class="text-sm text-surface-600 dark:text-surface-400">
        {{ archivoSeleccionado.name }}
      </div>

      <div class="flex gap-3">
        <Button
          label="Seleccionar imagen"
          icon="pi pi-upload"
          severity="secondary"
          size="small"
          @click="abrirSelector"
        />
        <Button
          v-if="archivoSeleccionado"
          label="Guardar foto"
          icon="pi pi-check"
          size="small"
          :loading="cargandoFoto"
          @click="guardarFoto"
        />
      </div>

      <Message v-if="exitoFoto" severity="success" :closable="false" class="w-full">
        Foto actualizada correctamente.
      </Message>
      <Message v-if="errorFoto" severity="error" :closable="false" class="w-full">
        {{ errorFoto }}
      </Message>
    </div>

    <!-- PESTAÑA: DATOS PERSONALES -->
    <div v-show="tabActiva === 'datos'" class="flex flex-col gap-4">
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium text-surface-700 dark:text-surface-300">Nombre</label>
        <InputText v-model="formularioDatos.nombre" placeholder="Tu nombre" />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium text-surface-700 dark:text-surface-300">Apellidos</label>
        <InputText v-model="formularioDatos.apellidos" placeholder="Tus apellidos" />
      </div>

      <Message v-if="exitoDatos" severity="success" :closable="false">
        Datos actualizados correctamente.
      </Message>
      <Message v-if="errorDatos" severity="error" :closable="false">
        {{ errorDatos }}
      </Message>

      <div class="flex justify-end">
        <Button
          label="Guardar cambios"
          icon="pi pi-check"
          :loading="cargandoDatos"
          @click="guardarDatos"
        />
      </div>

      <!-- Cambiar el email pide la contraseña: es con lo que se entra -->
      <div class="flex flex-col gap-4 border-t border-surface-200 dark:border-surface-700 pt-4">
        <div>
          <p class="text-sm font-medium text-surface-700 dark:text-surface-300">Correo electrónico</p>
          <p class="text-xs text-surface-500">Ahora: {{ userStore.perfil.email }}</p>
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-surface-700 dark:text-surface-300">Email nuevo</label>
          <InputText v-model="formularioEmail.nuevo" placeholder="tu@email.com" type="email" maxlength="150" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-surface-700 dark:text-surface-300">Contraseña actual</label>
          <Password v-model="formularioEmail.password" :feedback="false" toggleMask fluid />
        </div>

        <Message v-if="exitoEmail" severity="success" :closable="false">
          Email cambiado correctamente.
        </Message>
        <Message v-if="errorEmail" severity="error" :closable="false">
          {{ errorEmail }}
        </Message>

        <div class="flex justify-end">
          <Button
            label="Cambiar email"
            icon="pi pi-envelope"
            :disabled="!formularioEmail.nuevo || !formularioEmail.password"
            :loading="cargandoEmail"
            @click="guardarEmail"
          />
        </div>
      </div>
    </div>

    <!-- PESTAÑA: CONTRASEÑA -->
    <div v-show="tabActiva === 'contrasena'" class="flex flex-col gap-4">
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium text-surface-700 dark:text-surface-300">Contraseña actual</label>
        <Password v-model="formularioContrasena.actual" :feedback="false" toggleMask fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium text-surface-700 dark:text-surface-300">Nueva contraseña</label>
        <Password v-model="formularioContrasena.nueva" :feedback="false" toggleMask fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium text-surface-700 dark:text-surface-300">Confirmar nueva contraseña</label>
        <Password v-model="formularioContrasena.confirmar" :feedback="false" toggleMask fluid />
      </div>

      <Message v-if="exitoContrasena" severity="success" :closable="false">
        Contraseña cambiada correctamente.
      </Message>
      <Message v-if="errorContrasena" severity="error" :closable="false">
        {{ errorContrasena }}
      </Message>

      <div class="flex justify-end">
        <Button
          label="Cambiar contraseña"
          icon="pi pi-lock"
          :loading="cargandoContrasena"
          @click="guardarContrasena"
        />
      </div>
    </div>

    <!-- PESTAÑA: ELIMINAR CUENTA -->
    <div v-show="tabActiva === 'eliminar'" class="flex flex-col gap-5 py-4">
      <Message severity="warn" :closable="false" class="w-full">
        Esta acción es <strong>irreversible</strong>. Se eliminarán todos tus archivos, carpetas y datos de forma permanente.
      </Message>

      <div v-if="!confirmarEliminar" class="flex justify-center">
        <Button
          label="Quiero eliminar mi cuenta"
          icon="pi pi-trash"
          severity="danger"
          @click="confirmarEliminar = true"
        />
      </div>

      <div v-else class="flex flex-col gap-4 border border-red-300 dark:border-red-800 rounded-xl p-4 bg-red-50 dark:bg-red-950/30">
        <p class="text-sm text-surface-700 dark:text-surface-300">
          Escribe <strong>ELIMINAR</strong> para confirmar:
        </p>
        <InputText v-model="textoConfirmacion" placeholder="ELIMINAR" />
        <div class="flex flex-col gap-1">
          <label class="text-sm text-surface-700 dark:text-surface-300">Contraseña actual</label>
          <Password v-model="passwordEliminar" :feedback="false" toggleMask fluid />
        </div>
        <div class="flex gap-3 justify-end">
          <Button label="Cancelar" severity="secondary" @click="confirmarEliminar = false; textoConfirmacion = ''; passwordEliminar = ''" />
          <Button
            label="Eliminar cuenta"
            icon="pi pi-trash"
            severity="danger"
            :disabled="textoConfirmacion !== 'ELIMINAR' || !passwordEliminar"
            :loading="cargandoEliminar"
            @click="eliminarCuenta"
          />
        </div>
      </div>

      <Message v-if="errorEliminar" severity="error" :closable="false">
        {{ errorEliminar }}
      </Message>
    </div>

    <!-- Solo en móvil, que no tiene barra lateral; al pie para verse con cualquier pestaña -->
    <EspacioUsado class="sm:hidden mt-6 pt-4 border-t border-surface-200 dark:border-surface-700" />

  </Dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiUsers } from '@/api/users'
import { getErrorMessage } from '@/utils/errors'
import { useUserStore } from '@/stores/user'
import EspacioUsado from '@/components/EspacioUsado.vue'

import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Password from 'primevue/password'
import Message from 'primevue/message'

const visible = defineModel({ default: false })

const userStore = useUserStore()
const router = useRouter()

// Pestañas
const pestanas = [
  { clave: 'foto', etiqueta: 'Foto', icono: 'pi pi-image' },
  { clave: 'datos', etiqueta: 'Datos', icono: 'pi pi-id-card' },
  { clave: 'contrasena', etiqueta: 'Contraseña', icono: 'pi pi-lock' },
  { clave: 'eliminar', etiqueta: 'Eliminar', icono: 'pi pi-trash' },
]
const tabActiva = ref('foto')

watch(() => userStore.perfil, (valor) => {
  formularioDatos.value.nombre    = valor.nombre || ''
  formularioDatos.value.apellidos = valor.apellidos || ''
})

// === FOTO ==============================
const inputArchivo = ref(null)
const archivoSeleccionado = ref(null)
const urlPrevia = ref(null)
const cargandoFoto = ref(false)
const exitoFoto = ref(false)
const errorFoto = ref('')

const abrirSelector = () => inputArchivo.value?.click()

const alSeleccionarArchivo = (evento) => {
  const archivo = evento.target.files[0]
  if (!archivo) return
  archivoSeleccionado.value = archivo
  urlPrevia.value = URL.createObjectURL(archivo)
  exitoFoto.value = false
  errorFoto.value = ''
}

const guardarFoto = async () => {
  if (!archivoSeleccionado.value) return
  cargandoFoto.value = true
  errorFoto.value = ''
  exitoFoto.value = false
  try {
    const respuesta = await apiUsers.subirFotoPerfil(archivoSeleccionado.value)
    userStore.actualizarPerfil({ foto_perfil_url: respuesta.foto_perfil_url })
    exitoFoto.value = true
    archivoSeleccionado.value = null
  } catch (e) {
    errorFoto.value = getErrorMessage(e)
  } finally {
    cargandoFoto.value = false
  }
}

// === DATOS PERSONALES ==============================
const formularioDatos = ref({
  nombre: userStore.perfil.nombre || '',
  apellidos: userStore.perfil.apellidos || '',
})
const cargandoDatos = ref(false)
const exitoDatos    = ref(false)
const errorDatos    = ref('')

const guardarDatos = async () => {
  cargandoDatos.value = true
  errorDatos.value = ''
  exitoDatos.value = false
  try {
    const actualizado = await apiUsers.actualizarPerfil(formularioDatos.value)
    userStore.actualizarPerfil(actualizado)
    exitoDatos.value = true
  } catch (e) {
    errorDatos.value = getErrorMessage(e)
  } finally {
    cargandoDatos.value = false
  }
}

// === EMAIL ======================================
const formularioEmail = ref({ nuevo: '', password: '' })
const cargandoEmail   = ref(false)
const exitoEmail      = ref(false)
const errorEmail      = ref('')

const guardarEmail = async () => {
  cargandoEmail.value = true
  errorEmail.value = ''
  exitoEmail.value = false
  try {
    const actualizado = await apiUsers.cambiarEmail(
      formularioEmail.value.nuevo,
      formularioEmail.value.password,
    )
    userStore.actualizarPerfil(actualizado)
    exitoEmail.value = true
    formularioEmail.value = { nuevo: '', password: '' }
  } catch (e) {
    errorEmail.value = getErrorMessage(e)
  } finally {
    cargandoEmail.value = false
  }
}

// === CONTRASEÑA =================================
const formularioContrasena = ref({ actual: '', nueva: '', confirmar: '' })
const cargandoContrasena   = ref(false)
const exitoContrasena      = ref(false)
const errorContrasena      = ref('')

const guardarContrasena = async () => {
  errorContrasena.value = ''
  exitoContrasena.value = false
  if (formularioContrasena.value.nueva !== formularioContrasena.value.confirmar) {
    errorContrasena.value = 'Las contraseñas nuevas no coinciden.'
    return
  }
  cargandoContrasena.value = true
  try {
    await apiUsers.cambiarContrasena(
      formularioContrasena.value.actual,
      formularioContrasena.value.nueva,
    )
    exitoContrasena.value = true
    formularioContrasena.value = { actual: '', nueva: '', confirmar: '' }
  } catch (e) {
    errorContrasena.value = getErrorMessage(e)
  } finally {
    cargandoContrasena.value = false
  }
}

// === ELIMINAR CUENTA ===========================
const confirmarEliminar = ref(false)
const textoConfirmacion = ref('')
const passwordEliminar  = ref('')
const cargandoEliminar  = ref(false)
const errorEliminar     = ref('')

const eliminarCuenta = async () => {
  cargandoEliminar.value = true
  errorEliminar.value = ''
  try {
    await apiUsers.eliminarCuenta(passwordEliminar.value)
    // El backend ya cerró la sesión
    userStore.olvidarSesion()
    router.push('/')
  } catch (e) {
    errorEliminar.value = getErrorMessage(e)
  } finally {
    cargandoEliminar.value = false
  }
}

// Resetear todo al cerrar el modal
watch(visible, (valor) => {
  if (!valor) {
    tabActiva.value = 'foto'
    archivoSeleccionado.value = null
    urlPrevia.value = null
    exitoFoto.value = false
    errorFoto.value = ''
    exitoDatos.value = false
    errorDatos.value = ''
    formularioEmail.value = { nuevo: '', password: '' }
    exitoEmail.value = false
    errorEmail.value = ''
    formularioContrasena.value = { actual: '', nueva: '', confirmar: '' }
    exitoContrasena.value = false
    errorContrasena.value = ''
    confirmarEliminar.value = false
    textoConfirmacion.value = ''
    passwordEliminar.value = ''
    errorEliminar.value = ''
  }
})
</script>
