<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import PageHeader from '../components/common/PageHeader.vue'
import MetricCard from '../components/common/MetricCard.vue'
import DataTable from '../components/common/DataTable.vue'
import { useFormatters } from '../composables/useFormatters'
import { apiErrorMessage } from '../composables/useApiError'
import { api } from '../api/client'
import type { PlatformUser, PlatformTenant, PlatformStats } from '../types'

const auth = useAuthStore()
const { number, date, dash } = useFormatters()

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

// ── State ───────────────────────────────────────────────────────────────────

const users = ref<PlatformUser[]>([])
const tenants = ref<PlatformTenant[]>([])
const stats = ref<PlatformStats | null>(null)
const loading = ref(false)
const error = ref('')

const pendingUsers = computed(() => users.value.filter(u => u.status === 'pending_approval'))
const activeUsers = computed(() => users.value.filter(u => u.status !== 'pending_approval'))

// ── Loaders ─────────────────────────────────────────────────────────────────

async function run(label: string, fn: () => Promise<void>) {
  loading.value = true
  error.value = ''
  try {
    await fn()
  } catch (e) {
    error.value = apiErrorMessage(e, label)
  } finally {
    loading.value = false
  }
}

const loadUsers = () => run('Failed to load users', async () => { users.value = await api.platform.users() })
const loadTenants = () => run('Failed to load tenants', async () => { tenants.value = await api.platform.tenants() })
const loadStats = () => run('Failed to load stats', async () => { stats.value = await api.platform.stats() })

// ── Actions ─────────────────────────────────────────────────────────────────

async function act(label: string, fn: () => Promise<unknown>, reload: () => Promise<void>) {
  error.value = ''
  try {
    await fn()
    await reload()
  } catch (e) {
    error.value = apiErrorMessage(e, label)
  }
}

const toggleUserActive = (u: PlatformUser) =>
  act('Failed to update user', () => api.platform.updateUser(u.id, { is_active: !u.is_active }), loadUsers)
const toggleUserAdmin = (u: PlatformUser) =>
  act('Failed to update user', () => api.platform.updateUser(u.id, { is_admin: !u.is_admin }), loadUsers)
const approveUser = (u: PlatformUser) =>
  act('Failed to approve user', () => api.platform.approveUser(u.id), loadUsers)
const toggleTenantActive = (t: PlatformTenant) =>
  act('Failed to update tenant', () => api.platform.updateTenant(t.id, { is_active: !t.is_active }), loadTenants)

function formatDate(iso: string | null): string {
  return iso ? date(iso) : dash
}

function formatDateTime(iso: string | null): string {
  if (!iso) return dash
  return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
}

const statusClass = (status: string) =>
  status === 'active' ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400' :
  status === 'suspended' ? 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400' :
  'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400'

// ── Init ────────────────────────────────────────────────────────────────────

onMounted(() => {
  if (auth.user?.is_admin) loadUsers()
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
  <div v-else class="min-w-0">
    <PageHeader
      title="Admin Portal"
      subtitle="Approve sign-ins, manage users and tenants"
      tooltip="<strong>Admin Portal</strong><br>New Google sign-ins wait here until approved; approving creates their tenant. Deactivating a user or tenant takes effect at their next token refresh (within four hours)."
    >
      <template #below>
        <div class="flex flex-wrap gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 w-fit max-w-full">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            @click="switchTab(tab.key)"
            :aria-pressed="activeTab === tab.key"
            :class="[
              'min-h-10 px-4 py-2 text-sm font-medium rounded-md transition-colors',
              activeTab === tab.key
                ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300',
            ]"
          >
            {{ tab.label }}
            <span v-if="tab.badge" class="ml-1.5 px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-amber-500 text-white">{{ tab.badge }}</span>
          </button>
        </div>
      </template>
    </PageHeader>

    <!-- Error banner -->
    <div v-if="error" class="mb-4 p-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-400">
      {{ error }}
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-sm text-gray-400 dark:text-gray-500 py-8 text-center">Loading...</div>

    <!-- Pending Users tab -->
    <div v-else-if="activeTab === 'pending'">
      <div v-if="pendingUsers.length === 0" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-8 text-center">
        <p class="text-sm font-medium text-gray-700 dark:text-gray-300">No pending approvals</p>
        <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">New users who sign in with Google appear here for review.</p>
      </div>
      <div v-else class="space-y-3">
        <p class="text-xs text-gray-500 dark:text-gray-400">These users signed in with Google and are waiting for approval. Approving creates a tenant and gives them access.</p>
        <div v-for="u in pendingUsers" :key="u.id"
          class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3">
          <div class="min-w-0">
            <div class="text-sm font-medium text-gray-900 dark:text-white truncate">{{ u.display_name }}</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5 break-words">
              {{ u.email }} &middot; {{ u.auth_provider }} &middot; Signed up {{ formatDate(u.created_at) }}
            </div>
          </div>
          <div class="flex gap-2">
            <button @click="approveUser(u)"
              class="min-h-10 px-4 py-2 text-xs font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 transition-colors">
              Approve
            </button>
            <button @click="toggleUserActive(u)"
              class="min-h-10 px-3 py-2 text-xs font-medium rounded-lg text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors">
              Reject
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- All Users tab -->
    <div v-else-if="activeTab === 'users'" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2">
      <DataTable :empty="activeUsers.length === 0" empty-text="No users found." :columns="8">
        <thead>
          <tr>
            <th>Email</th>
            <th>Name</th>
            <th>Status</th>
            <th>Provider</th>
            <th>Admin</th>
            <th>Tenants</th>
            <th>Last Login</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in activeUsers" :key="u.id">
            <td class="whitespace-nowrap">
              <RouterLink :to="`/admin-portal/users/${u.id}`" class="text-indigo-600 dark:text-indigo-400 hover:underline">{{ u.email }}</RouterLink>
            </td>
            <td class="whitespace-nowrap">{{ u.display_name }}</td>
            <td><span :class="['inline-block px-2 py-0.5 text-xs font-medium rounded-full', statusClass(u.status)]">{{ u.status }}</span></td>
            <td><span class="inline-block px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">{{ u.auth_provider }}</span></td>
            <td>
              <span :class="[
                'inline-block px-2 py-0.5 text-xs font-medium rounded-full',
                u.is_admin ? 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-500',
              ]">{{ u.is_admin ? 'Yes' : 'No' }}</span>
            </td>
            <td>
              <div class="flex flex-wrap gap-1">
                <span v-if="u.tenants.length === 0" class="text-gray-400 dark:text-gray-500">{{ dash }}</span>
                <span v-for="name in u.tenants" :key="name"
                  class="inline-block px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 whitespace-nowrap">{{ name }}</span>
              </div>
            </td>
            <td class="text-xs whitespace-nowrap">{{ formatDateTime(u.last_login) }}</td>
            <td>
              <div class="flex gap-1 whitespace-nowrap">
                <button @click="toggleUserActive(u)"
                  :class="['min-h-10 px-2 py-1 text-xs font-medium rounded transition-colors', u.is_active ? 'text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30' : 'text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-950/30']"
                >{{ u.is_active ? 'Deactivate' : 'Activate' }}</button>
                <button @click="toggleUserAdmin(u)"
                  class="min-h-10 px-2 py-1 text-xs font-medium rounded text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 transition-colors"
                >{{ u.is_admin ? 'Remove Admin' : 'Make Admin' }}</button>
              </div>
            </td>
          </tr>
        </tbody>
      </DataTable>
    </div>

    <!-- Tenants tab -->
    <div v-else-if="activeTab === 'tenants'" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2">
      <DataTable :empty="tenants.length === 0" empty-text="No tenants found." :columns="8">
        <thead>
          <tr>
            <th>Name</th>
            <th>Owner</th>
            <th>Slug</th>
            <th>Schema</th>
            <th>Active</th>
            <th>Members</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in tenants" :key="t.id">
            <td class="font-medium whitespace-nowrap">
              <RouterLink :to="`/admin-portal/tenants/${t.id}`" class="text-indigo-600 dark:text-indigo-400 hover:underline">{{ t.display_name }}</RouterLink>
            </td>
            <td>
              <div v-if="t.owner_email" class="whitespace-nowrap">
                <div class="text-gray-900 dark:text-gray-100">{{ t.owner_name || dash }}</div>
                <div class="text-xs text-gray-500 dark:text-gray-400">{{ t.owner_email }}</div>
              </div>
              <span v-else class="text-gray-400 dark:text-gray-500">{{ dash }}</span>
            </td>
            <td class="font-mono text-xs">{{ t.slug }}</td>
            <td class="font-mono text-xs">{{ t.schema_name }}</td>
            <td><span :class="['inline-block w-2 h-2 rounded-full', t.is_active ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600']"></span></td>
            <td>{{ t.member_count }}</td>
            <td class="text-xs whitespace-nowrap">{{ formatDate(t.created_at) }}</td>
            <td>
              <button @click="toggleTenantActive(t)"
                :class="['min-h-10 px-2 py-1 text-xs font-medium rounded transition-colors whitespace-nowrap', t.is_active ? 'text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30' : 'text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-950/30']"
              >{{ t.is_active ? 'Deactivate' : 'Activate' }}</button>
            </td>
          </tr>
        </tbody>
      </DataTable>
    </div>

    <!-- Stats tab -->
    <div v-else-if="activeTab === 'stats'">
      <div v-if="stats" class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Total Users" :value="number(stats.total_users, 0)" />
        <MetricCard label="Active Users" :value="number(stats.active_users, 0)" />
        <MetricCard label="Total Tenants" :value="number(stats.total_tenants, 0)" />
        <MetricCard label="Active Tenants" :value="number(stats.active_tenants, 0)" />
      </div>
      <div v-else-if="!loading" class="text-sm text-gray-400 dark:text-gray-500 py-8 text-center">No stats available.</div>
    </div>
  </div>
</template>
