import { h } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

// Route state is introduced before the legacy screen is split into page files.
// The shell remains mounted so active chat/session state is not lost during the
// incremental migration.
const RouteStateHost = { render: () => h('span', { class: 'route-state-host', 'aria-hidden': 'true' }) }

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/workspace/agents' },
    { path: '/workspace/agents', name: 'workspace-agents', component: RouteStateHost },
    { path: '/workspace/agents/:id/chat', name: 'workspace-agent-chat', component: RouteStateHost },
    { path: '/console', name: 'console-overview', component: RouteStateHost },
    { path: '/console/agents', name: 'console-agents', component: RouteStateHost },
    { path: '/console/agents/:id/edit', name: 'console-agent-edit', component: RouteStateHost },
    { path: '/console/capabilities', name: 'console-capabilities', component: RouteStateHost },
    { path: '/console/capabilities/:id', name: 'console-capability-detail', component: RouteStateHost },
    { path: '/console/knowledge', name: 'console-knowledge', component: RouteStateHost },
    { path: '/console/knowledge/:id', name: 'console-knowledge-detail', component: RouteStateHost },
    { path: '/console/connections', name: 'console-connections', component: RouteStateHost },
    { path: '/console/connections/:id', name: 'console-connection-detail', component: RouteStateHost },
    { path: '/console/runs', name: 'console-runs', component: RouteStateHost },
    { path: '/console/runs/:id', name: 'console-run-detail', component: RouteStateHost },
    { path: '/console/governance', name: 'console-governance', component: RouteStateHost },
    { path: '/:pathMatch(.*)*', redirect: '/workspace/agents' },
  ],
})
