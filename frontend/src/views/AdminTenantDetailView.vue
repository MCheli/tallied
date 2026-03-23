<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const auth = useAuthStore()

const API = '/api/v1'

interface TenantMember {
  user_id: number
  email: string
  display_name: string
  role: string
  is_default: boolean
}

interface TenantDetail {
  id: number
  display_name: string
  slug: string
  schema_name: string
  is_active: boolean
  created_at: string | null
  members: TenantMember[]
  table_counts: Record<string, number>
}

const tenant = ref<TenantDetail | null>(null)
const loading = ref(false)
const error = ref('')
const actionLoading = ref(false)

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    ...options,
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

async function loadTenant() {
  loading.value = true
  error.value = ''
  try {
    tenant.value = await fetchJson<TenantDetail>(`/platform/tenants/${route.params.id}`)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to load tenant'
  } finally {
    loading.value = false
  }
}

async function toggleActive() {
  if (!tenant.value) return
  actionLoading.value = true
  try {
    await fetchJson(`/platform/tenants/${tenant.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({ is_active: !tenant.value.is_active }),
    })
    await loadTenant()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to update tenant'
  } finally {
    actionLoading.value = false
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

function totalRows(counts: Record<string, number>): number {
  return Object.values(counts).reduce((sum, n) => sum + n, 0)
}

onMounted(() => {
  if (auth.user?.is_admin) {
    loadTenant()
  }
})
</script>

<template>
  <!-- Access denied -->
  <div v-if="!auth.user?.is_admin" class="flex items-center justify-center h-[60vh]">
    <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-8 text-center max-w-md">
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-2">Access Denied</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400">You do not have admin privileges to view this page.</p>
    </div>
  </div>

  <div v-else>
    <!-- Back link -->
    <div class="mb-4">
      <RouterLink to="/admin-portal" class="text-sm text-indigo-600 dark:text-indigo-400 hover:underline">
        &larr; Back to Admin Portal
      </RouterLink>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-sm text-gray-400 dark:text-gray-500 py-8 text-center">Loading...</div>

    <!-- Error -->
    <div v-if="error" class="mb-4 p-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-400">
      {{ error }}
    </div>

    <div v-if="tenant && !loading">
      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">{{ tenant.display_name }}</h1>
        <button
          @click="toggleActive"
          :disabled="actionLoading"
          :class="[
            'px-4 py-2 text-xs font-medium rounded-lg border transition-colors disabled:opacity-50',
            tenant.is_active
              ? 'border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30'
              : 'border-green-300 dark:border-green-700 text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-950/30',
          ]"
        >{{ tenant.is_active ? 'Deactivate' : 'Activate' }}</button>
      </div>

      <!-- Tenant info card -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 mb-6">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-4">Tenant Info</h2>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Display Name</p>
            <p class="text-sm text-gray-900 dark:text-gray-100">{{ tenant.display_name }}</p>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Slug</p>
            <p class="text-sm text-gray-900 dark:text-gray-100 font-mono">{{ tenant.slug }}</p>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Schema</p>
            <p class="text-sm text-gray-900 dark:text-gray-100 font-mono">{{ tenant.schema_name }}</p>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Active</p>
            <span :class="[
              'inline-block px-2 py-0.5 text-xs font-medium rounded-full',
              tenant.is_active
                ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400'
                : 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400',
            ]">{{ tenant.is_active ? 'Yes' : 'No' }}</span>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Created</p>
            <p class="text-sm text-gray-900 dark:text-gray-100">{{ formatDate(tenant.created_at) }}</p>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Members</p>
            <p class="text-sm text-gray-900 dark:text-gray-100">{{ tenant.members.length }}</p>
          </div>
        </div>
      </div>

      <!-- Members table -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden mb-6">
        <div class="px-4 py-3 border-b border-gray-100 dark:border-gray-800">
          <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Members</h2>
        </div>
        <table class="w-full text-left">
          <thead>
            <tr class="border-b border-gray-100 dark:border-gray-800">
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Email</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Name</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Role</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Default</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50 dark:divide-gray-800">
            <tr v-for="m in tenant.members" :key="m.user_id" class="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
              <td class="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">
                <RouterLink :to="`/admin-portal/users/${m.user_id}`" class="text-indigo-600 dark:text-indigo-400 hover:underline">
                  {{ m.email }}
                </RouterLink>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ m.display_name }}</td>
              <td class="px-4 py-3">
                <span class="inline-block px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
                  {{ m.role }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span v-if="m.is_default" class="inline-block w-2 h-2 rounded-full bg-green-500"></span>
                <span v-else class="inline-block w-2 h-2 rounded-full bg-gray-300 dark:bg-gray-600"></span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="tenant.members.length === 0" class="p-8 text-center text-sm text-gray-400 dark:text-gray-500">
          No members.
        </div>
      </div>

      <!-- Schema stats -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
          <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Schema Stats</h2>
          <span v-if="Object.keys(tenant.table_counts).length > 0" class="text-xs text-gray-400 dark:text-gray-500">
            {{ totalRows(tenant.table_counts).toLocaleString() }} total rows
          </span>
        </div>
        <div v-if="Object.keys(tenant.table_counts).length > 0">
          <table class="w-full text-left">
            <thead>
              <tr class="border-b border-gray-100 dark:border-gray-800">
                <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Table</th>
                <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 text-right">Rows</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-50 dark:divide-gray-800">
              <tr v-for="(count, table) in tenant.table_counts" :key="table" class="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                <td class="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 font-mono">{{ table }}</td>
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400 text-right">{{ count.toLocaleString() }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="p-8 text-center text-sm text-gray-400 dark:text-gray-500">
          No table data available (schema stats require PostgreSQL).
        </div>
      </div>
    </div>
  </div>
</template>
