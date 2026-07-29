import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'home', component: () => import('../views/HomeView.vue') },
  { path: '/module/:id', name: 'module-edit', component: () => import('../views/ModuleEditView.vue'), props: true },
  { path: '/analysis', name: 'analysis', component: () => import('../views/AnalysisView.vue') },
  { path: '/result/:id', name: 'result', component: () => import('../views/ResultView.vue'), props: true },
  { path: '/history', name: 'history', component: () => import('../views/HistoryView.vue') },
  { path: '/history/:id', name: 'history-detail', component: () => import('../views/HistoryDetailView.vue'), props: true },
  { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
