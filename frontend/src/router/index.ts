import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      name: 'dashboard',
      component: () => import('../views/DashboardView.vue'),
    },
    {
      path: '/spending',
      name: 'spending',
      component: () => import('../views/SpendingView.vue'),
    },
    {
      path: '/cash',
      name: 'cash',
      component: () => import('../views/CashView.vue'),
    },
    {
      path: '/assets',
      name: 'assets',
      component: () => import('../views/AssetsView.vue'),
    },
    {
      path: '/property',
      name: 'property',
      component: () => import('../views/PropertyView.vue'),
    },
    {
      path: '/retirement',
      name: 'retirement',
      component: () => import('../views/RetirementView.vue'),
    },
    {
      path: '/planning',
      name: 'planning',
      component: () => import('../views/PlanningView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue'),
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('../views/DatabaseView.vue'),
    },
    {
      path: '/income',
      name: 'income',
      component: () => import('../views/IncomeView.vue'),
    },
    {
      path: '/rsu',
      name: 'rsu',
      component: () => import('../views/RSUView.vue'),
    },
    {
      path: '/guide',
      name: 'guide',
      component: () => import('../views/GuideView.vue'),
    },
  ],
})

// Auth guard — redirect to login if not authenticated
router.beforeEach(async (to) => {
  if (to.meta.public) return true

  // Check auth status
  const { useAuthStore } = await import('../stores/auth')
  const auth = useAuthStore()

  if (!auth.authenticated && !auth.loading) {
    await auth.checkAuth()
  }

  // For now, allow unauthenticated access (auth is opt-in)
  // Uncomment below to enforce login:
  // if (!auth.authenticated && to.name !== 'login') {
  //   return { name: 'login' }
  // }

  return true
})

export default router
