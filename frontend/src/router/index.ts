import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    public?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { public: true, title: 'Sign In' },
    },
    {
      path: '/pending-approval',
      name: 'pending-approval',
      component: () => import('../views/PendingApprovalView.vue'),
      meta: { public: true, title: 'Pending Approval' },
    },
    {
      path: '/',
      name: 'dashboard',
      component: () => import('../views/DashboardView.vue'),
      meta: { title: 'Dashboard' },
    },
    {
      path: '/recap',
      name: 'recap',
      component: () => import('../views/RecapView.vue'),
      meta: { title: 'Weekly Recap' },
    },
    {
      path: '/spending',
      name: 'spending',
      component: () => import('../views/SpendingView.vue'),
      meta: { title: 'Spending' },
    },
    {
      path: '/cash',
      name: 'cash',
      component: () => import('../views/CashView.vue'),
      meta: { title: 'Cash' },
    },
    {
      path: '/assets',
      name: 'assets',
      component: () => import('../views/AssetsView.vue'),
      meta: { title: 'Assets' },
    },
    {
      path: '/property',
      name: 'property',
      component: () => import('../views/PropertyView.vue'),
      meta: { title: 'Property' },
    },
    {
      path: '/retirement',
      name: 'retirement',
      component: () => import('../views/RetirementView.vue'),
      meta: { title: '401(k)' },
    },
    {
      path: '/planning',
      name: 'planning',
      component: () => import('../views/PlanningView.vue'),
      meta: { title: 'Planning' },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue'),
      meta: { title: 'Settings' },
    },
    {
      path: '/database',
      name: 'database',
      component: () => import('../views/DatabaseView.vue'),
      meta: { title: 'Database' },
    },
    {
      path: '/income',
      name: 'income',
      component: () => import('../views/IncomeView.vue'),
      meta: { title: 'Income' },
    },
    {
      path: '/rsu',
      name: 'rsu',
      component: () => import('../views/RSUView.vue'),
      meta: { title: 'RSU' },
    },
    {
      path: '/developer',
      name: 'developer',
      component: () => import('../views/ApiView.vue'),
      meta: { title: 'API' },
    },
    {
      path: '/guide',
      name: 'guide',
      component: () => import('../views/GuideView.vue'),
      meta: { title: 'Guide' },
    },
    {
      path: '/admin-portal',
      name: 'admin-portal',
      component: () => import('../views/AdminPortalView.vue'),
      meta: { title: 'Admin Portal' },
    },
    {
      path: '/admin-portal/users/:id',
      name: 'admin-user-detail',
      component: () => import('../views/AdminUserDetailView.vue'),
      meta: { title: 'User Detail' },
    },
    {
      path: '/admin-portal/tenants/:id',
      name: 'admin-tenant-detail',
      component: () => import('../views/AdminTenantDetailView.vue'),
      meta: { title: 'Tenant Detail' },
    },
  ],
})

// Auth guard — redirect to login if not authenticated
router.beforeEach(async (to) => {
  if (to.meta.public) return true

  const auth = useAuthStore()

  if (!auth.authenticated) {
    await auth.checkAuth()
  }

  if (!auth.authenticated && to.name !== 'login') {
    return { name: 'login' }
  }

  // Authenticated but no tenant = pending approval
  if (auth.authenticated && auth.user && !auth.user.current_tenant && to.name !== 'pending-approval') {
    return { name: 'pending-approval' }
  }

  return true
})

// Dynamic page title
router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} — Tallied` : 'Tallied'
})

// After a deploy, a tab opened earlier still asks for the old page chunks, which no longer exist, and the
// navigation fails silently (the tap "does nothing"). Load the app fresh at the page that was asked for.
export function isChunkLoadError(err: unknown): boolean {
  const msg = err instanceof Error ? err.message : String(err)
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i.test(msg)
}

router.onError((err, to) => {
  if (!isChunkLoadError(err)) return
  const key = 'tallied-chunk-reload'
  try {
    if (sessionStorage.getItem(key) === to.fullPath) return   // already reloaded once for this page; don't loop
    sessionStorage.setItem(key, to.fullPath)
  } catch { /* storage blocked: reload anyway */ }
  window.location.assign(to.fullPath)
})

export default router
