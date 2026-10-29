<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import PageHeader from '../components/common/PageHeader.vue'
import MetricCard from '../components/common/MetricCard.vue'
import DataTable from '../components/common/DataTable.vue'
import { useFormatters } from '../composables/useFormatters'
import { apiErrorMessage } from '../composables/useApiError'
import { api } from '../api/client'
import type { PlatformUserDetail } from '../types'

const route = useRoute()
const auth = useAuthStore()
const { number, date, dash } = useFormatters()

const user = ref<PlatformUserDetail | null>(null)
const loading = ref(false)
const error = ref('')
const actionLoading = ref(false)

async function loadUser() {
  loading.value = true
  error.value = ''
  try {
    user.value = await api.platform.user(String(route.params.id))
  } catch (e) {
    error.value = apiErrorMessage(e, 'Failed to load user')
  } finally {
    loading.value = false
  }
}

async function act(label: string, fn: () => Promise<unknown>) {
  if (!user.value) return
  actionLoading.value = true
  error.value = ''
  try {
    await fn()
    await loadUser()
  } catch (e) {
    error.value = apiErrorMessage(e, label)
  } finally {
    actionLoading.value = false
  }
}

const toggleAdmin = () => act('Failed to update user', () => api.platform.updateUser(user.value!.id, { is_admin: !user.value!.is_admin }))
const toggleActive = () => act('Failed to update user', () => api.platform.updateUser(user.value!.id, { is_active: !user.value!.is_active }))
const approveUser = () => act('Failed to approve user', () => api.platform.approveUser(user.value!.id))

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

onMounted(() => {
  if (auth.user?.is_admin) loadUser()
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

  <div v-else class="min-w-0">
    <div class="mb-4">
      <RouterLink to="/admin-portal" class="inline-flex min-h-10 items-center text-sm text-indigo-600 dark:text-indigo-400 hover:underline">
        &larr; Back to Admin Portal
      </RouterLink>
    </div>

    <div v-if="loading" class="text-sm text-gray-400 dark:text-gray-500 py-8 text-center">Loading...</div>

    <div v-if="error" class="mb-4 p-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-400">
      {{ error }}
    </div>

    <div v-if="user && !loading">
      <PageHeader :title="user.display_name" :subtitle="user.email">
        <button
          v-if="user.status === 'pending_approval'"
          @click="approveUser"
          :disabled="actionLoading"
          class="min-h-10 px-4 py-2 text-xs font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 transition-colors disabled:opacity-50"
        >Approve</button>
        <button
          @click="toggleAdmin"
          :disabled="actionLoading"
          class="min-h-10 px-4 py-2 text-xs font-medium rounded-lg border border-indigo-300 dark:border-indigo-700 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 transition-colors disabled:opacity-50"
        >{{ user.is_admin ? 'Remove Admin' : 'Make Admin' }}</button>
        <button
          @click="toggleActive"
          :disabled="actionLoading"
          :class="[
            'min-h-10 px-4 py-2 text-xs font-medium rounded-lg border transition-colors disabled:opacity-50',
            user.is_active
              ? 'border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30'
              : 'border-green-300 dark:border-green-700 text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-950/30',
          ]"
        >{{ user.is_active ? 'Deactivate' : 'Activate' }}</button>
      </PageHeader>

      <!-- User info card -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 mb-6">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-4">User Info</h2>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="min-w-0">
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Email</p>
            <p class="text-sm text-gray-900 dark:text-gray-100 break-all">{{ user.email }}</p>
          </div>
          <div class="min-w-0">
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Display Name</p>
            <p class="text-sm text-gray-900 dark:text-gray-100 truncate">{{ user.display_name }}</p>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Auth Provider</p>
            <span class="inline-block px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">{{ user.auth_provider }}</span>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Status</p>
            <span :class="['inline-block px-2 py-0.5 text-xs font-medium rounded-full', statusClass(user.status)]">{{ user.status }}</span>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Admin</p>
            <span :class="['inline-block px-2 py-0.5 text-xs font-medium rounded-full', user.is_admin ? 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-500']">{{ user.is_admin ? 'Yes' : 'No' }}</span>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Active</p>
            <span :class="['inline-block px-2 py-0.5 text-xs font-medium rounded-full', user.is_active ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400' : 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400']">{{ user.is_active ? 'Yes' : 'No' }}</span>
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
        <MetricCard label="API Keys" :value="number(user.api_key_count, 0)" />
        <MetricCard label="DB Credentials" :value="number(user.db_credential_count, 0)" />
      </div>

      <!-- Tenant memberships -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 py-3">Tenant Memberships</h2>
        <DataTable :empty="user.tenants.length === 0" empty-text="No tenant memberships." :columns="4">
          <thead>
            <tr>
              <th>Tenant</th>
              <th>Slug</th>
              <th>Role</th>
              <th>Default</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in user.tenants" :key="t.tenant_id">
              <td class="font-medium whitespace-nowrap">
                <RouterLink :to="`/admin-portal/tenants/${t.tenant_id}`" class="text-indigo-600 dark:text-indigo-400 hover:underline">{{ t.display_name }}</RouterLink>
              </td>
              <td class="font-mono text-xs">{{ t.slug }}</td>
              <td><span class="inline-block px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">{{ t.role }}</span></td>
              <td><span :class="['inline-block w-2 h-2 rounded-full', t.is_default ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600']"></span></td>
            </tr>
          </tbody>
        </DataTable>
      </div>
    </div>
  </div>
</template>
