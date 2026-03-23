<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const auth = useAuthStore()

const API = '/api/v1'

interface TenantMembership {
  tenant_id: number
  display_name: string
  slug: string
  role: string
  is_default: boolean
}

interface UserDetail {
  id: number
  email: string
  display_name: string
  auth_provider: string
  is_admin: boolean
  is_active: boolean
  status: string
  created_at: string | null
  last_login: string | null
  tenants: TenantMembership[]
  api_key_count: number
  db_credential_count: number
}

const user = ref<UserDetail | null>(null)
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

async function loadUser() {
  loading.value = true
  error.value = ''
  try {
    user.value = await fetchJson<UserDetail>(`/platform/users/${route.params.id}`)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to load user'
  } finally {
    loading.value = false
  }
}

async function toggleAdmin() {
  if (!user.value) return
  actionLoading.value = true
  try {
    await fetchJson(`/platform/users/${user.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({ is_admin: !user.value.is_admin }),
    })
    await loadUser()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to update user'
  } finally {
    actionLoading.value = false
  }
}

async function toggleActive() {
  if (!user.value) return
  actionLoading.value = true
  try {
    await fetchJson(`/platform/users/${user.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({ is_active: !user.value.is_active }),
    })
    await loadUser()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to update user'
  } finally {
    actionLoading.value = false
  }
}

async function approveUser() {
  if (!user.value) return
  actionLoading.value = true
  try {
    await fetchJson(`/platform/users/${user.value.id}/approve`, { method: 'POST' })
    await loadUser()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to approve user'
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

onMounted(() => {
  if (auth.user?.is_admin) {
    loadUser()
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

    <div v-if="user && !loading">
      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">{{ user.display_name }}</h1>
        <div class="flex gap-2">
          <button
            v-if="user.status === 'pending_approval'"
            @click="approveUser"
            :disabled="actionLoading"
            class="px-4 py-2 text-xs font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 transition-colors disabled:opacity-50"
          >Approve</button>
          <button
            @click="toggleAdmin"
            :disabled="actionLoading"
            class="px-4 py-2 text-xs font-medium rounded-lg border border-indigo-300 dark:border-indigo-700 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 transition-colors disabled:opacity-50"
          >{{ user.is_admin ? 'Remove Admin' : 'Make Admin' }}</button>
          <button
            @click="toggleActive"
            :disabled="actionLoading"
            :class="[
              'px-4 py-2 text-xs font-medium rounded-lg border transition-colors disabled:opacity-50',
              user.is_active
                ? 'border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30'
                : 'border-green-300 dark:border-green-700 text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-950/30',
            ]"
          >{{ user.is_active ? 'Deactivate' : 'Activate' }}</button>
        </div>
      </div>

      <!-- User info card -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 mb-6">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-4">User Info</h2>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Email</p>
            <p class="text-sm text-gray-900 dark:text-gray-100">{{ user.email }}</p>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Display Name</p>
            <p class="text-sm text-gray-900 dark:text-gray-100">{{ user.display_name }}</p>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Auth Provider</p>
            <span class="inline-block px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
              {{ user.auth_provider }}
            </span>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Status</p>
            <span :class="[
              'inline-block px-2 py-0.5 text-xs font-medium rounded-full',
              user.status === 'active' ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400' :
              user.status === 'suspended' ? 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400' :
              'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400'
            ]">{{ user.status }}</span>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Admin</p>
            <span :class="[
              'inline-block px-2 py-0.5 text-xs font-medium rounded-full',
              user.is_admin
                ? 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-500',
            ]">{{ user.is_admin ? 'Yes' : 'No' }}</span>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Active</p>
            <span :class="[
              'inline-block px-2 py-0.5 text-xs font-medium rounded-full',
              user.is_active
                ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400'
                : 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400',
            ]">{{ user.is_active ? 'Yes' : 'No' }}</span>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Created</p>
            <p class="text-sm text-gray-900 dark:text-gray-100">{{ formatDate(user.created_at) }}</p>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Last Login</p>
            <p class="text-sm text-gray-900 dark:text-gray-100">{{ formatDateTime(user.last_login) }}</p>
          </div>
        </div>
      </div>

      <!-- Counts row -->
      <div class="grid grid-cols-2 gap-4 mb-6">
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <p class="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">API Keys</p>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">{{ user.api_key_count }}</p>
        </div>
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <p class="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">DB Credentials</p>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">{{ user.db_credential_count }}</p>
        </div>
      </div>

      <!-- Tenant memberships -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-100 dark:border-gray-800">
          <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Tenant Memberships</h2>
        </div>
        <table class="w-full text-left">
          <thead>
            <tr class="border-b border-gray-100 dark:border-gray-800">
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Tenant</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Slug</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Role</th>
              <th class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Default</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50 dark:divide-gray-800">
            <tr v-for="t in user.tenants" :key="t.tenant_id" class="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
              <td class="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 font-medium">
                <RouterLink :to="`/admin-portal/tenants/${t.tenant_id}`" class="text-indigo-600 dark:text-indigo-400 hover:underline">
                  {{ t.display_name }}
                </RouterLink>
              </td>
              <td class="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 font-mono text-xs">{{ t.slug }}</td>
              <td class="px-4 py-3">
                <span class="inline-block px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
                  {{ t.role }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span v-if="t.is_default" class="inline-block w-2 h-2 rounded-full bg-green-500"></span>
                <span v-else class="inline-block w-2 h-2 rounded-full bg-gray-300 dark:bg-gray-600"></span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="user.tenants.length === 0" class="p-8 text-center text-sm text-gray-400 dark:text-gray-500">
          No tenant memberships.
        </div>
      </div>
    </div>
  </div>
</template>
