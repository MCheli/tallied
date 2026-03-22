<script setup lang="ts">
import { ref, computed, onMounted, type Component } from 'vue'
import { useRoute, useRouter, RouterLink, RouterView } from 'vue-router'
import ImportModal from './components/import/ImportModal.vue'
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

type NavItem = { to: string; name: string; label: string; icon: Component }
const navGroups: { group: string; items: NavItem[] }[] = [
  {
    group: 'Overview',
    items: [
      { to: '/', name: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    ],
  },
  {
    group: 'Money',
    items: [
      { to: '/spending', name: 'spending', label: 'Spending', icon: CreditCard },
      { to: '/income', name: 'income', label: 'Income', icon: DollarSign },
    ],
  },
  {
    group: 'Wealth',
    items: [
      { to: '/cash', name: 'cash', label: 'Cash', icon: Wallet },
      { to: '/rsu', name: 'rsu', label: 'RSU', icon: Gem },
      { to: '/retirement', name: 'retirement', label: '401(k)', icon: PiggyBank },
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
    group: 'System',
    items: [
      { to: '/settings', name: 'settings', label: 'Settings', icon: Settings },
      { to: '/admin', name: 'admin', label: 'Database', icon: Database },
      { to: '/guide', name: 'guide', label: 'Guide', icon: BookOpen },
    ],
  },
]

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
      <div class="px-5 py-6">
        <h1 class="text-xl font-bold tracking-tight text-gray-900 dark:text-white">Tallied</h1>
      </div>
      <nav class="flex-1 px-3 space-y-0.5">
        <template v-for="(group, gi) in navGroups" :key="group.group">
          <div v-if="gi > 0" class="pt-3 pb-1">
            <div class="border-t border-gray-100 dark:border-gray-800 mb-2"></div>
            <span class="px-3 text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-semibold">{{ group.group }}</span>
          </div>
          <RouterLink
            v-for="item in group.items"
            :key="item.name"
            :to="item.to"
            :class="[
              'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
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
      <div class="px-3 pb-4 space-y-1">
        <button
          @click="toggleDark"
          class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          <component :is="dark ? Sun : Moon" class="w-4 h-4" />
          <span>{{ dark ? 'Light Mode' : 'Dark Mode' }}</span>
        </button>
        <div v-if="auth.authenticated" class="flex items-center justify-between px-3 py-2">
          <span class="text-xs text-gray-500 dark:text-gray-400 truncate">{{ auth.user?.display_name }}</span>
          <button @click="auth.logout(); router.push('/login')" class="text-gray-400 hover:text-red-500">
            <LogOut class="w-3.5 h-3.5" />
          </button>
        </div>
        <RouterLink v-else to="/login"
          class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
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
