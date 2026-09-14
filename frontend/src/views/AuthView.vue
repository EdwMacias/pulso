<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowUpRight, AudioLines, Check, ArrowRight } from 'lucide-vue-next'
import { useSession } from '../stores/session'
import { api } from '../services/api'
const route = useRoute(), router = useRouter(), session = useSession()
const email = ref(''), password = ref(''), busy = ref(false), error = ref(''), notice = ref('')
const mode = computed(() => route.path)
const title = computed(() => ({ '/registro': 'Un buen día empieza aquí.', '/recuperar': 'Recupera tu acceso.', '/restablecer': 'Tu nueva contraseña.', '/verificar': 'Verifica tu correo.' }[mode.value] || 'Qué bueno tenerte de vuelta.'))
const label = computed(() => ({ '/registro': 'Crear mi cuenta', '/recuperar': 'Enviar enlace', '/restablecer': 'Guardar contraseña', '/verificar': 'Verificar mi correo' }[mode.value] || 'Entrar'))
async function resend() {
  if (!email.value) { error.value='Introduce tu correo electrónico para reenviar la verificación.'; return }
  busy.value=true; error.value=''
  try { await api('/auth/resend-verification', { method:'POST', body:JSON.stringify({ email:email.value }) }); notice.value='Si tu cuenta necesita verificación, recibirás un nuevo enlace.' }
  catch(e) { error.value=(e as Error).message } finally { busy.value=false }
}
async function submit() {
  busy.value = true; error.value = ''; notice.value = ''
  try {
    if (mode.value === '/recuperar') { await api('/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email: email.value }) }); notice.value = 'Si existe una cuenta, recibirás instrucciones para recuperar el acceso.' }
    else if (mode.value === '/verificar') { await api('/auth/verify-email', { method: 'POST', body: JSON.stringify({ token: route.query.token }) }); notice.value = 'Correo verificado. Ya puedes iniciar sesión.' }
    else if (mode.value === '/restablecer') { await api('/auth/reset-password', { method: 'POST', body: JSON.stringify({ token: route.query.token, password: password.value }) }); notice.value = 'Contraseña actualizada. Ya puedes iniciar sesión.' }
    else {
      const data = await session.authenticate(mode.value === '/registro' ? 'register' : 'login', email.value, password.value)
      if (data.verification_required) notice.value = 'Revisa tu correo para activar la cuenta.'
      else await router.push('/')
    }
  } catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
</script>
<template>
  <main class="auth-page">
    <section class="auth-story"><a class="brand light" href="/">pulso<span>✳</span></a><div><p class="eyebrow">TU DÍA, CON INTENCIÓN</p><h1>Menos pendientes<br>en la cabeza.<br><em>Más vida.</em></h1><p class="story-copy">Un espacio para ordenar tus tareas, recordar lo importante y avanzar a tu ritmo.</p><div class="story-note"><AudioLines :size="27" /><div><strong>Tu próxima idea empieza hablando.</strong><span>El asistente que estamos construyendo contigo.</span></div></div></div><footer><span>Un paso a la vez también es avanzar.</span><ArrowUpRight :size="20" /></footer></section>
    <section class="auth-form"><div class="form-wrap"><p class="eyebrow green">BIENVENIDO A TU ESPACIO</p><h2>{{ title }}</h2><p class="muted">{{ mode === '/registro' ? 'Crea tu cuenta y empieza a darle espacio a lo importante.' : 'Tus tareas y próximos pasos, en un solo lugar.' }}</p>
      <form @submit.prevent="submit">
        <label v-if="!['/verificar', '/restablecer'].includes(mode)">Correo electrónico<input v-model="email" type="email" autocomplete="email" placeholder="tu@correo.com" required maxlength="254"></label>
        <label v-if="!['/recuperar', '/verificar'].includes(mode)">Contraseña<input v-model="password" type="password" :autocomplete="mode === '/login' ? 'current-password' : 'new-password'" placeholder="Al menos 12 caracteres" required minlength="12" maxlength="128"></label>
        <RouterLink v-if="mode === '/login'" to="/recuperar" class="small-link">Olvidé mi contraseña</RouterLink>
        <button v-if="mode === '/login' || mode === '/registro'" type="button" class="small-link" :disabled="busy" @click="resend">Reenviar verificación de correo</button>
        <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="notice" role="status"><Check :size="16" />{{ notice }}</p>
        <button class="primary full" :disabled="busy">{{ busy ? 'Un momento…' : label }}<ArrowRight :size="18" /></button>
      </form>
      <p class="auth-switch">{{ mode === '/login' ? '¿Es tu primera vez?' : '¿Ya tienes una cuenta?' }} <RouterLink :to="mode === '/login' ? '/registro' : '/login'">{{ mode === '/login' ? 'Crea tu cuenta' : 'Inicia sesión' }}</RouterLink></p>
      <p class="privacy-note">Tu espacio es personal. Tus tareas solo son visibles para ti.</p>
    </div></section>
  </main>
</template>
