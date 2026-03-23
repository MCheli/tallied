import { createRouter, createWebHistory } from 'vue-router'

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

  // Check auth status
  const { useAuthStore } = await import('../stores/auth')
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

export default router
