<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

const API = '/api/v1'

type Tab = 'pending' | 'users' | 'tenants' | 'stats'
const activeTab = ref<Tab>('pending')
const tabs = computed(() => {
  const t: { key: Tab; label: string; badge?: number }[] = [
    { key: 'pending', label: 'Pending Users', badge: pendingUsers.value.length },
    { key: 'users', label: 'All Users' },
    { key: 'tenants', label: 'Tenants' },
    { key: 'stats', label: 'Stats' },
  ]
  return t
})

// ── Types ───────────────────────────────────────────────────────────────────

interface PlatformUser {
  id: number
  email: string
  display_name: string
  auth_provider: string
  is_admin: boolean
  is_active: boolean
  status: string
  created_at: string | null
  last_login: string | null
  tenant_count: number
  tenants: string[]
}

interface PlatformTenant {
  id: number
  display_name: string
  slug: string
  schema_name: string
  is_active: boolean
  created_at: string | null
  member_count: number
  owner_email: string | null
  owner_name: string | null
}

interface PlatformStats {
  total_users: number
  active_users: number
  total_tenants: number
  active_tenants: number
}

// ── State ───────────────────────────────────────────────────────────────────

const users = ref<PlatformUser[]>([])
const tenants = ref<PlatformTenant[]>([])
const stats = ref<PlatformStats | null>(null)
const loading = ref(false)
const error = ref('')

const pendingUsers = computed(() => users.value.filter(u => u.status === 'pending_approval'))
const activeUsers = computed(() => users.value.filter(u => u.status !== 'pending_approval'))

// ── Fetchers ────────────────────────────────────────────────────────────────

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    ...options,
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    users.value = await fetchJson<PlatformUser[]>('/platform/users')
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to load users'
  } finally {
    loading.value = false
  }
}

async function loadTenants() {
  loading.value = true
  error.value = ''
  try {
    tenants.value = await fetchJson<PlatformTenant[]>('/platform/tenants')
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to load tenants'
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  loading.value = true
  error.value = ''
  try {
    stats.value = await fetchJson<PlatformStats>('/platform/stats')
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to load stats'
  } finally {
    loading.value = false
  }
}

// ── Actions ─────────────────────────────────────────────────────────────────

async function toggleUserActive(user: PlatformUser) {
  try {
    await fetchJson(`/platform/users/${user.id}`, {
      method: 'PUT',
      body: JSON.stringify({ is_active: !user.is_active }),
    })
    await loadUsers()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to update user'
  }
}

async function toggleUserAdmin(user: PlatformUser) {
  try {
    await fetchJson(`/platform/users/${user.id}`, {
      method: 'PUT',
      body: JSON.stringify({ is_admin: !user.is_admin }),
    })
    await loadUsers()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to update user'
  }
}

async function approveUser(user: PlatformUser) {
  try {
    await fetchJson(`/platform/users/${user.id}/approve`, { method: 'POST' })
    await loadUsers()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to approve user'
  }
}

async function toggleTenantActive(tenant: PlatformTenant) {
  try {
    await fetchJson(`/platform/tenants/${tenant.id}`, {
      method: 'PUT',
      body: JSON.stringify({ is_active: !tenant.is_active }),
    })
    await loadTenants()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to update tenant'
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return '--'
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '--'
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

// ── Init ────────────────────────────────────────────────────────────────────

onMounted(() => {
  if (auth.user?.is_admin) {
    loadUsers()
  }
})

function switchTab(tab: Tab) {
  activeTab.value = tab
  if ((tab === 'users' || tab === 'pending') && users.value.length === 0) loadUsers()
  if (tab === 'tenants' && tenants.value.length === 0) loadTenants()
  if (tab === 'stats' && !stats.value) loadStats()
}
</script>

<template>
  <!-- Access denied -->
  <div v-if="!auth.user?.is_admin" class="flex items-center justify-center h-[60vh]">
    <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-8 text-center max-w-md">
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-2">Access Denied</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400">You do not have admin privileges to view this page.</p>
    </div>
  </div>

  <!-- Admin portal -->
  <div v-else>
    <h1 class="text-2xl font-bold text-gray-900 dark:text-white mb-6">Admin Portal</h1>

    <!-- Tab bar -->
    <div class="flex gap-1 mb-6 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 w-fit">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        @click="switchTab(tab.key)"
        :class="[
          'px-4 py-2 text-sm font-medium rounded-md transition-colors',
          activeTab === tab.key
            ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
            : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300',
        ]"
      >
        {{ tab.label }}
        <span v-if="tab.badge" class="ml-1.5 px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-amber-500 text-white">{{ tab.badge }}</span>
      </button>
    </div>

    <!-- Error banner -->
    <div v-if="error" class="mb-4 p-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-400">
      {{ error }}
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-sm text-gray-400 dark:text-gray-500 py-8 text-center">Loading...</div>

    <!-- Pending Users tab -->
    <div v-else-if="activeTab === 'pending'">
      <div v-if="pendingUsers.length === 0" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-8 text-center">
        <div class="text-3xl mb-3">&#x2705;</div>
        <p class="text-sm font-medium text-gray-700 dark:text-gray-300">No pending approvals</p>
        <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">New users who sign up via Google SSO will appear here for review.</p>
      </div>
      <div v-else class="space-y-3">
        <p class="text-xs text-gray-500 dark:text-gray-400">These users signed up via Google SSO and are waiting for you to approve their account. Approving creates a tenant and gives them access to the platform.</p>
        <div v-for="u in pendingUsers" :key="u.id"
          class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div class="text-sm font-medium text-gray-900 dark:text-white">{{ u.display_name }}</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              {{ u.email }} &middot; {{ u.auth_provider }} &middot; Signed up {{ formatDate(u.created_at) }}
            </div>
          </div>
          <div class="flex gap-2">
            <button @click="approveUser(u)"
              class="px-4 py-2 text-xs font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 transition-colors">
              Approve
            </button>
            <button @click="toggleUserActive(u)"
              class="px-3 py-2 text-xs font-medium rounded-lg text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors">
              Reject
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- All Users tab -->
    <div v-else-if="activeTab === 'users'">
      <!-- All users table -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        <table class="w-full text-left">
          <thead>
            <tr class="border-b border-gray-100 dark:border-gray-800">
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Email</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Name</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Status</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Provider</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Admin</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Tenants</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Last Login</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50 dark:divide-gray-800">
            <tr v-for="u in activeUsers" :key="u.id" class="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
              <td class="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">
                <RouterLink :to="`/admin-portal/users/${u.id}`" class="text-indigo-600 dark:text-indigo-400 hover:underline">{{ u.email }}</RouterLink>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ u.display_name }}</td>
              <td class="px-4 py-3">
                <span :class="[
                  'inline-block px-2 py-0.5 text-xs font-medium rounded-full',
                  u.status === 'active' ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400' :
                  u.status === 'suspended' ? 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400' :
                  'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400'
                ]">{{ u.status }}</span>
              </td>
              <td class="px-4 py-3">
                <span class="inline-block px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
                  {{ u.auth_provider }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span :class="[
                  'inline-block px-2 py-0.5 text-xs font-medium rounded-full',
                  u.is_admin
                    ? 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-500',
                ]">{{ u.is_admin ? 'Yes' : 'No' }}</span>
              </td>
              <td class="px-4 py-3">
                <div class="flex flex-wrap gap-1">
                  <span v-if="u.tenants.length === 0" class="text-sm text-gray-400 dark:text-gray-500">--</span>
                  <span
                    v-for="name in u.tenants"
                    :key="name"
                    class="inline-block px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300"
                  >{{ name }}</span>
                </div>
              </td>
              <td class="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">{{ formatDateTime(u.last_login) }}</td>
              <td class="px-4 py-3">
                <div class="flex gap-2">
                  <button
                    @click="toggleUserActive(u)"
                    :class="[
                      'px-2 py-1 text-xs font-medium rounded transition-colors',
                      u.is_active
                        ? 'text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30'
                        : 'text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-950/30',
                    ]"
                  >{{ u.is_active ? 'Deactivate' : 'Activate' }}</button>
                  <button
                    @click="toggleUserAdmin(u)"
                    class="px-2 py-1 text-xs font-medium rounded text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 transition-colors"
                  >{{ u.is_admin ? 'Remove Admin' : 'Make Admin' }}</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="activeUsers.length === 0 && !loading" class="p-8 text-center text-sm text-gray-400 dark:text-gray-500">
          No users found.
        </div>
      </div>
    </div>

    <!-- Tenants tab -->
    <div v-else-if="activeTab === 'tenants'">
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        <table class="w-full text-left">
          <thead>
            <tr class="border-b border-gray-100 dark:border-gray-800">
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Name</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Owner</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Slug</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Schema</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Active</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Members</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Created</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50 dark:divide-gray-800">
            <tr v-for="t in tenants" :key="t.id" class="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
              <td class="px-4 py-3 text-sm font-medium">
                <RouterLink :to="`/admin-portal/tenants/${t.id}`" class="text-indigo-600 dark:text-indigo-400 hover:underline">{{ t.display_name }}</RouterLink>
              </td>
              <td class="px-4 py-3">
                <div v-if="t.owner_email" class="text-sm">
                  <div class="text-gray-900 dark:text-gray-100">{{ t.owner_name || '--' }}</div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">{{ t.owner_email }}</div>
                </div>
                <span v-else class="text-sm text-gray-400 dark:text-gray-500">--</span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 font-mono text-xs">{{ t.slug }}</td>
              <td class="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 font-mono text-xs">{{ t.schema_name }}</td>
              <td class="px-4 py-3">
                <span :class="[
                  'inline-block w-2 h-2 rounded-full',
                  t.is_active ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600',
                ]"></span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ t.member_count }}</td>
              <td class="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">{{ formatDate(t.created_at) }}</td>
              <td class="px-4 py-3">
                <button
                  @click="toggleTenantActive(t)"
                  :class="[
                    'px-2 py-1 text-xs font-medium rounded transition-colors',
                    t.is_active
                      ? 'text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30'
                      : 'text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-950/30',
                  ]"
                >
                  {{ t.is_active ? 'Deactivate' : 'Activate' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="tenants.length === 0 && !loading" class="p-8 text-center text-sm text-gray-400 dark:text-gray-500">
          No tenants found.
        </div>
      </div>
    </div>

    <!-- Stats tab -->
    <div v-else-if="activeTab === 'stats'">
      <div v-if="stats" class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <p class="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">Total Users</p>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">{{ stats.total_users }}</p>
        </div>
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <p class="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">Active Users</p>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">{{ stats.active_users }}</p>
        </div>
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <p class="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">Total Tenants</p>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">{{ stats.total_tenants }}</p>
        </div>
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <p class="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">Active Tenants</p>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">{{ stats.active_tenants }}</p>
        </div>
      </div>
      <div v-else-if="!loading" class="text-sm text-gray-400 dark:text-gray-500 py-8 text-center">
        No stats available.
      </div>
    </div>
  </div>
</template>
