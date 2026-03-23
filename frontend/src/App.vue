<script setup lang="ts">
import { ref, computed, onMounted, type Component } from 'vue'
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
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const dark = ref(localStorage.getItem('theme') === 'dark')

onMounted(() => {
  auth.checkAuth()
})

function toggleDark() {
  dark.value = !dark.value
  document.documentElement.classList.toggle('dark', dark.value)
  localStorage.setItem('theme', dark.value ? 'dark' : 'light')
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
</script>

<template>
  <!-- Login page: no sidebar -->
  <div v-if="currentRoute === 'login'" class="h-screen bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100">
    <RouterView />
  </div>

  <!-- App layout: sidebar + content -->
  <div v-else class="flex h-screen bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100">
    <!-- Sidebar -->
    <aside class="w-56 flex-shrink-0 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col">
      <div class="px-5 py-4">
        <h1 class="text-xl font-bold tracking-tight text-gray-900 dark:text-white">Tallied</h1>
      </div>
      <nav class="sidebar-nav flex-1 overflow-y-auto px-3 space-y-0.5">
        <template v-for="(group, gi) in filteredNavGroups" :key="group.group">
          <div v-if="gi > 0" class="pt-2 pb-0.5">
            <div class="border-t border-gray-100 dark:border-gray-800 mb-1"></div>
            <span class="px-3 text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-semibold">{{ group.group }}</span>
          </div>
          <RouterLink
            v-for="item in group.items"
            :key="item.name"
            :to="item.to"
            :class="[
              'flex items-center gap-3 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
              currentRoute === item.name
                ? 'bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300'
                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-200'
            ]"
          >
            <component :is="item.icon" class="w-4 h-4" />
            <span>{{ item.label }}</span>
          </RouterLink>
        </template>
      </nav>
      <div class="px-3 pb-3 space-y-0.5">
        <button
          @click="toggleDark"
          class="w-full flex items-center gap-3 px-3 py-1.5 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          <component :is="dark ? Sun : Moon" class="w-4 h-4" />
          <span>{{ dark ? 'Light Mode' : 'Dark Mode' }}</span>
        </button>
        <TenantSwitcher />
        <div v-if="auth.authenticated">
          <button
            @click="auth.logout(); router.push('/login')"
            class="w-full flex items-center gap-3 px-3 py-1.5 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-red-50 dark:hover:bg-red-950/30 hover:text-red-600 dark:hover:text-red-400 transition-colors"
          >
            <LogOut class="w-4 h-4" />
            <span>Sign out</span>
          </button>
          <div class="px-3 py-1.5">
            <span class="text-[10px] text-gray-400 dark:text-gray-500 truncate block">{{ auth.user?.display_name }}</span>
          </div>
        </div>
        <RouterLink v-else to="/login"
          class="w-full flex items-center gap-3 px-3 py-1.5 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
          Sign in
        </RouterLink>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="flex-1 overflow-y-auto">
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
</style>
