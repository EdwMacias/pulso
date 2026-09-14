import { createRouter, createWebHistory } from 'vue-router'
import { useSession } from './stores/session'
import AuthView from './views/AuthView.vue'
import WorkspaceView from './views/WorkspaceView.vue'
export const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/login', component: AuthView }, { path: '/registro', component: AuthView },
  { path: '/recuperar', component: AuthView }, { path: '/verificar', component: AuthView }, { path: '/restablecer', component: AuthView },
  ...['/', '/agenda', '/asistente', '/actividad', '/ajustes'].map(path => ({ path, component: WorkspaceView, meta: { authenticated: true } })),
  { path: '/:pathMatch(.*)*', redirect: '/' },
] })
router.beforeEach(async to => {
  const session = useSession()
  if (!session.loaded) { try { await session.restore() } catch { /* Login can display connection errors on submission. */ } }
  if (to.meta.authenticated && !session.user) return '/login'
  if (session.user && ['/login', '/registro'].includes(to.path)) return '/'
})
