<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, type Component } from 'vue'
import { useRoute, useRouter, RouterLink, RouterView } from 'vue-router'
import ImportModal from './components/import/ImportModal.vue'
import TenantSwitcher from './components/common/TenantSwitcher.vue'
import { useAuthStore } from './stores/auth'
import {
  LayoutDashboard,
  LogOut,
  CreditCard,
  Target,
  DollarSign,
  Gem,
  Settings,
  Database,
  BookOpen,
  Sun,
  Moon,
  Wallet,
  Home,
  Car,
  PiggyBank,
  KeyRound,
  Shield,
  Menu,
  X,
  PanelLeftClose,
  PanelLeftOpen,
  LogIn,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const dark = ref(localStorage.getItem('theme') === 'dark')

// Sidebar state
const mobileOpen = ref(false)
const collapsed = ref(localStorage.getItem('sidebar-collapsed') === 'true')
const isMobile = ref(typeof window !== 'undefined' ? window.innerWidth < 768 : false)

function checkMobile() {
  isMobile.value = window.innerWidth < 768
  if (!isMobile.value) mobileOpen.value = false
}

onMounted(() => {
  auth.checkAuth()
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

// Close mobile sidebar on route change
watch(() => route.path, () => {
  mobileOpen.value = false
})

function toggleDark() {
  dark.value = !dark.value
  document.documentElement.classList.toggle('dark', dark.value)
  localStorage.setItem('theme', dark.value ? 'dark' : 'light')
}

function toggleCollapsed() {
  collapsed.value = !collapsed.value
  localStorage.setItem('sidebar-collapsed', collapsed.value ? 'true' : 'false')
}

// Apply on load
if (dark.value) document.documentElement.classList.add('dark')

type NavItem = { to: string; name: string; label: string; icon: Component; adminOnly?: boolean }
const navGroups: { group: string; items: NavItem[] }[] = [
  {
    group: 'Overview',
    items: [
      { to: '/', name: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
      { to: '/guide', name: 'guide', label: 'Guide', icon: BookOpen },
    ],
  },
  {
    group: 'Money',
    items: [
      { to: '/spending', name: 'spending', label: 'Spending', icon: CreditCard },
      { to: '/income', name: 'income', label: 'Income', icon: DollarSign },
      { to: '/cash', name: 'cash', label: 'Cash', icon: Wallet },
    ],
  },
  {
    group: 'Investments',
    items: [
      { to: '/rsu', name: 'rsu', label: 'RSU', icon: Gem },
      { to: '/retirement', name: 'retirement', label: '401(k)', icon: PiggyBank },
    ],
  },
  {
    group: 'Property',
    items: [
      { to: '/property', name: 'property', label: 'Property', icon: Home },
      { to: '/assets', name: 'assets', label: 'Assets', icon: Car },
    ],
  },
  {
    group: 'Planning',
    items: [
      { to: '/planning', name: 'planning', label: 'Planning', icon: Target },
    ],
  },
  {
    group: 'Platform',
    items: [
      { to: '/database', name: 'database', label: 'Database', icon: Database },
      { to: '/developer', name: 'developer', label: 'API', icon: KeyRound },
      { to: '/settings', name: 'settings', label: 'Settings', icon: Settings },
      { to: '/admin-portal', name: 'admin-portal', label: 'Admin Portal', icon: Shield, adminOnly: true },
    ],
  },
]

const filteredNavGroups = computed(() => {
  const isAdmin = auth.user?.is_admin ?? false
  return navGroups.map(group => ({
    ...group,
    items: group.items.filter(item => !item.adminOnly || isAdmin),
  })).filter(group => group.items.length > 0)
})

const currentRoute = computed(() => route.name)

const showLabels = computed(() => isMobile.value || !collapsed.value)
</script>

<template>
  <!-- Login page: no sidebar -->
  <div v-if="currentRoute === 'login'" class="h-screen bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100">
    <RouterView />
  </div>

  <!-- App layout: sidebar + content -->
  <div v-else class="flex h-screen bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100">

    <!-- Mobile top bar -->
    <div class="md:hidden fixed top-0 left-0 right-0 z-40 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 flex items-center px-4 h-14">
      <button
        @click="mobileOpen = true"
        aria-label="Open navigation menu"
        class="p-1.5 -ml-1.5 rounded-lg text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
      >
        <Menu class="w-5 h-5" />
      </button>
      <h1 class="ml-3 text-lg font-bold tracking-tight text-gray-900 dark:text-white">Tallied</h1>
    </div>

    <!-- Mobile backdrop -->
    <Transition name="fade">
      <div
        v-if="mobileOpen"
        class="md:hidden fixed inset-0 z-40 bg-black/50"
        @click="mobileOpen = false"
      />
    </Transition>

    <!-- Sidebar -->
    <aside
      :class="[
        'flex-shrink-0 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col transition-all duration-200',
        // Mobile: fixed overlay drawer
        'max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-50 max-md:w-64 max-md:shadow-xl',
        mobileOpen ? 'max-md:translate-x-0' : 'max-md:-translate-x-full',
        // Desktop: inline, collapsible
        collapsed ? 'md:w-16' : 'md:w-56',
      ]"
    >
      <div class="flex items-center justify-between px-5 py-4">
        <h1 v-if="showLabels" class="text-xl font-bold tracking-tight text-gray-900 dark:text-white">Tallied</h1>
        <!-- Mobile close button -->
        <button
          v-if="isMobile"
          @click="mobileOpen = false"
          aria-label="Close navigation menu"
          class="p-1 rounded-lg text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          <X class="w-5 h-5" />
        </button>
        <!-- Desktop collapse toggle -->
        <button
          v-if="!isMobile"
          @click="toggleCollapsed"
          class="p-1 rounded-lg text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          :title="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
          :aria-label="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
        >
          <PanelLeftClose v-if="!collapsed" class="w-4 h-4" />
          <PanelLeftOpen v-else class="w-4 h-4" />
        </button>
      </div>

      <nav class="sidebar-nav flex-1 overflow-y-auto px-3 space-y-0.5">
        <template v-for="(group, gi) in filteredNavGroups" :key="group.group">
          <div v-if="gi > 0" class="pt-2 pb-0.5">
            <div class="border-t border-gray-100 dark:border-gray-800 mb-1"></div>
            <span v-if="showLabels" class="px-3 text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-semibold">{{ group.group }}</span>
          </div>
          <RouterLink
            v-for="item in group.items"
            :key="item.name"
            :to="item.to"
            :title="collapsed && !isMobile ? item.label : undefined"
            :aria-label="collapsed && !isMobile ? item.label : undefined"
            :class="[
              'flex items-center rounded-lg text-sm font-medium transition-colors',
              collapsed && !isMobile ? 'justify-center px-0 py-2' : 'gap-3 px-3 py-1.5',
              currentRoute === item.name
                ? 'bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300'
                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-200'
            ]"
          >
            <component :is="item.icon" class="w-4 h-4 flex-shrink-0" />
            <span v-if="showLabels">{{ item.label }}</span>
          </RouterLink>
        </template>
      </nav>

      <div class="px-3 pb-3 space-y-0.5">
        <button
          @click="toggleDark"
          :title="collapsed && !isMobile ? (dark ? 'Light Mode' : 'Dark Mode') : undefined"
          :aria-label="dark ? 'Switch to light mode' : 'Switch to dark mode'"
          :class="[
            'w-full flex items-center rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors',
            collapsed && !isMobile ? 'justify-center px-0 py-2' : 'gap-3 px-3 py-1.5',
          ]"
        >
          <component :is="dark ? Sun : Moon" class="w-4 h-4 flex-shrink-0" />
          <span v-if="showLabels">{{ dark ? 'Light Mode' : 'Dark Mode' }}</span>
        </button>
        <TenantSwitcher :collapsed="!showLabels" />
        <div v-if="auth.authenticated">
          <button
            @click="auth.logout(); router.push('/login')"
            :title="collapsed && !isMobile ? 'Sign out' : undefined"
            aria-label="Sign out"
            :class="[
              'w-full flex items-center rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-red-50 dark:hover:bg-red-950/30 hover:text-red-600 dark:hover:text-red-400 transition-colors',
              collapsed && !isMobile ? 'justify-center px-0 py-2' : 'gap-3 px-3 py-1.5',
            ]"
          >
            <LogOut class="w-4 h-4 flex-shrink-0" />
            <span v-if="showLabels">Sign out</span>
          </button>
          <div v-if="showLabels" class="px-3 py-1.5">
            <span class="text-[10px] text-gray-400 dark:text-gray-500 truncate block">{{ auth.user?.display_name }}</span>
          </div>
        </div>
        <RouterLink v-else to="/login"
          aria-label="Sign in"
          :title="collapsed && !isMobile ? 'Sign in' : undefined"
          :class="[
            'w-full flex items-center rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors',
            collapsed && !isMobile ? 'justify-center px-0 py-2' : 'gap-3 px-3 py-1.5',
          ]"
        >
          <LogIn class="w-4 h-4 flex-shrink-0" />
          <span v-if="showLabels">Sign in</span>
        </RouterLink>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="flex-1 overflow-y-auto max-md:pt-14">
      <div class="p-6 max-w-[1600px] mx-auto">
        <RouterView />
      </div>
    </main>
    <ImportModal />
  </div>
</template>

<style scoped>
.sidebar-nav::-webkit-scrollbar { display: none; }
.sidebar-nav { -ms-overflow-style: none; scrollbar-width: none; }

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
