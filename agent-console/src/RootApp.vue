<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import App from './App.vue'
import DeveloperWorkbench from './pages/developer/DeveloperWorkbench.vue'
import ExternalCapabilityOnboarding from './pages/developer/ExternalCapabilityOnboarding.vue'
import ResourcePlayground from './pages/developer/ResourcePlayground.vue'

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
interface CommonResourceInstallResponse {
  created: number
  existing: number
  items: Array<{ display_name: string; status: string }>
}

const session = ref<SessionPayload | null>(null)
const developerEnabled = ref(false)
const developerWorkspaceActive = ref(true)
const developerWorkbenchKey = ref(0)
const installingCommon = ref(false)
const commonNotice = ref('')
const onboardingOpen = ref(false)
const playgroundOpen = ref(false)
let timer: number | undefined

const isKnownAdmin = computed(() => Boolean(session.value?.principal.role_codes.some(role => role === 'admin' || role === 'agent_admin')))

async function probeSession() {
  try {
    const response = await fetch('/api/v1/auth/session', { credentials: 'same-origin' })
    if (!response.ok) {
      session.value = null
      developerEnabled.value = false
      developerWorkspaceActive.value = true
      onboardingOpen.value = false
      playgroundOpen.value = false
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

function resourcesChanged() {
  developerWorkbenchKey.value += 1
  commonNotice.value = '资源目录已刷新。新接入能力现在可以进入 Playground 或 Agent Builder。'
  window.setTimeout(() => { commonNotice.value = '' }, 3600)
}

async function installCommonResources() {
  if (!session.value || installingCommon.value) return
  installingCommon.value = true
  commonNotice.value = ''
  try {
    const response = await fetch('/api/v1/developer/resources/common/install', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': session.value.csrf_token },
    })
    const payload = await response.json().catch(() => ({})) as Partial<CommonResourceInstallResponse> & { message?: string; detail?: string }
    if (!response.ok) throw new Error(payload.message || payload.detail || `HTTP ${response.status}`)
    commonNotice.value = `常用资源已就绪：新增 ${payload.created || 0}，已有 ${payload.existing || 0}`
    developerWorkbenchKey.value += 1
    window.setTimeout(() => { commonNotice.value = '' }, 3600)
  } catch (err) {
    commonNotice.value = err instanceof Error ? `安装失败：${err.message}` : '常用资源安装失败'
  } finally {
    installingCommon.value = false
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
    developerWorkspaceActive.value = true
    onboardingOpen.value = false
    playgroundOpen.value = false
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
  <template v-if="developerEnabled && session && developerWorkspaceActive">
    <DeveloperWorkbench
      :key="developerWorkbenchKey"
      :principal="session.principal"
      :csrf-token="session.csrf_token"
      @logout="logoutDeveloper"
    />
    <div class="root-developer-actions">
      <span v-if="commonNotice" class="common-notice">{{ commonNotice }}</span>
      <button class="root-workspace-switch onboard" @click="onboardingOpen = true">接入外部能力</button>
      <button class="root-workspace-switch playground" @click="playgroundOpen = true">Resource Playground</button>
      <button class="root-workspace-switch common" :disabled="installingCommon" @click="installCommonResources">{{ installingCommon ? '正在添加…' : '添加常用资源' }}</button>
      <button class="root-workspace-switch use" @click="developerWorkspaceActive = false">使用工作台</button>
    </div>
  </template>
  <template v-else>
    <App />
    <button v-if="developerEnabled && session" class="root-workspace-switch develop" @click="developerWorkspaceActive = true">开发工作台</button>
  </template>

  <ExternalCapabilityOnboarding
    v-if="developerEnabled && session && onboardingOpen"
    :principal="session.principal"
    :csrf-token="session.csrf_token"
    @close="onboardingOpen = false"
    @installed="resourcesChanged"
  />
  <ResourcePlayground
    v-if="developerEnabled && session && playgroundOpen"
    :csrf-token="session.csrf_token"
    @close="playgroundOpen = false"
  />
</template>

<style scoped>
.root-developer-actions {
  position: fixed;
  right: 22px;
  bottom: 22px;
  z-index: 80;
  display: flex;
  align-items: center;
  gap: 8px;
}
.root-workspace-switch {
  border: 0;
  border-radius: 999px;
  padding: 11px 16px;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 10px 28px rgba(16, 24, 40, .18);
}
.root-workspace-switch:disabled { opacity: .65; cursor: default; }
.root-workspace-switch.use { color: #4338ca; background: white; }
.root-workspace-switch.common { color: white; background: #111827; }
.root-workspace-switch.onboard { color: white; background: #6941c6; }
.root-workspace-switch.playground { color: #101828; background: #d1fadf; }
.root-workspace-switch.develop {
  position: fixed;
  right: 22px;
  bottom: 22px;
  z-index: 80;
  color: white;
  background: #5b4ee5;
}
.common-notice {
  max-width: 360px;
  padding: 9px 12px;
  border-radius: 10px;
  background: rgba(17, 24, 39, .94);
  color: #fff;
  font-size: 12px;
  box-shadow: 0 10px 28px rgba(16, 24, 40, .18);
}
@media (max-width: 920px) {
  .root-developer-actions { left: 14px; right: 14px; justify-content: flex-end; flex-wrap: wrap; }
  .common-notice { width: 100%; max-width: none; }
}
</style>