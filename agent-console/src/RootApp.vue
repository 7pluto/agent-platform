<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import App from './App.vue'
import DeveloperWorkbench from './pages/developer/DeveloperWorkbench.vue'

interface SessionPrincipal {
  external_user_id: string
  display_name: string
  role_codes: string[]
  dept_ids: string[]
}
interface SessionPayload {
  principal: SessionPrincipal
  csrf_token: string
}

const session = ref<SessionPayload | null>(null)
const developerEnabled = ref(false)
let timer: number | undefined

const isKnownAdmin = computed(() => Boolean(session.value?.principal.role_codes.some(role => role === 'admin' || role === 'agent_admin')))

async function probeSession() {
  try {
    const response = await fetch('/api/v1/auth/session', { credentials: 'same-origin' })
    if (!response.ok) {
      session.value = null
      developerEnabled.value = false
      return
    }
    const payload = await response.json() as SessionPayload
    session.value = payload
    if (payload.principal.role_codes.some(role => role === 'admin' || role === 'agent_admin')) {
      developerEnabled.value = false
      return
    }
    const developer = await fetch('/api/v1/developer/resources/context', { credentials: 'same-origin' })
    developerEnabled.value = developer.ok
  } catch {
    session.value = null
    developerEnabled.value = false
  }
}

async function logoutDeveloper() {
  const csrf = session.value?.csrf_token || ''
  try {
    await fetch('/api/v1/auth/logout', {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrf ? { 'X-CSRF-Token': csrf } : {},
    })
  } finally {
    session.value = null
    developerEnabled.value = false
    window.location.assign('/')
  }
}

onMounted(() => {
  void probeSession()
  // App.vue owns the login screen. During development we keep this tiny probe so
  // a RuoYi developer is switched into the resource workbench immediately after login.
  timer = window.setInterval(() => {
    if (!developerEnabled.value && !isKnownAdmin.value) void probeSession()
  }, 1200)
})
onBeforeUnmount(() => { if (timer !== undefined) window.clearInterval(timer) })
</script>

<template>
  <DeveloperWorkbench
    v-if="developerEnabled && session"
    :principal="session.principal"
    :csrf-token="session.csrf_token"
    @logout="logoutDeveloper"
  />
  <App v-else />
</template>
