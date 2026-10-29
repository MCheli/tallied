<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import PageHeader from '../components/common/PageHeader.vue'
import DataTable from '../components/common/DataTable.vue'
import { useFormatters } from '../composables/useFormatters'
import { apiErrorMessage } from '../composables/useApiError'
import { api } from '../api/client'
import type { PlatformTenantDetail } from '../types'

const route = useRoute()
const auth = useAuthStore()
const { number, date, dash } = useFormatters()

const tenant = ref<PlatformTenantDetail | null>(null)
const loading = ref(false)
const error = ref('')
const actionLoading = ref(false)

async function loadTenant() {
  loading.value = true
  error.value = ''
  try {
    tenant.value = await api.platform.tenant(String(route.params.id))
  } catch (e) {
    error.value = apiErrorMessage(e, 'Failed to load tenant')
  } finally {
    loading.value = false
  }
}

async function toggleActive() {
  if (!tenant.value) return
  actionLoading.value = true
  error.value = ''
  try {
    await api.platform.updateTenant(tenant.value.id, { is_active: !tenant.value.is_active })
    await loadTenant()
  } catch (e) {
    error.value = apiErrorMessage(e, 'Failed to update tenant')
  } finally {
    actionLoading.value = false
  }
}

function formatDate(iso: string | null): string {
  return iso ? date(iso) : dash
}

function totalRows(counts: Record<string, number>): number {
  return Object.values(counts).reduce((sum, n) => sum + n, 0)
}

onMounted(() => {
  if (auth.user?.is_admin) loadTenant()
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

    <div v-if="tenant && !loading">
      <PageHeader :title="tenant.display_name" :subtitle="`${tenant.schema_name} · ${tenant.members.length} member${tenant.members.length === 1 ? '' : 's'}`">
        <button
          @click="toggleActive"
          :disabled="actionLoading"
          :class="[
            'min-h-10 px-4 py-2 text-xs font-medium rounded-lg border transition-colors disabled:opacity-50',
            tenant.is_active
              ? 'border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30'
              : 'border-green-300 dark:border-green-700 text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-950/30',
          ]"
        >{{ tenant.is_active ? 'Deactivate' : 'Activate' }}</button>
      </PageHeader>

      <!-- Tenant info card -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 mb-6">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-4">Tenant Info</h2>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="min-w-0">
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Display Name</p>
            <p class="text-sm text-gray-900 dark:text-gray-100 truncate">{{ tenant.display_name }}</p>
          </div>
          <div class="min-w-0">
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Slug</p>
            <p class="text-sm text-gray-900 dark:text-gray-100 font-mono truncate">{{ tenant.slug }}</p>
          </div>
          <div class="min-w-0">
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Schema</p>
            <p class="text-sm text-gray-900 dark:text-gray-100 font-mono truncate">{{ tenant.schema_name }}</p>
          </div>
          <div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mb-1">Active</p>
            <span :class="['inline-block px-2 py-0.5 text-xs font-medium rounded-full', tenant.is_active ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400' : 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400']">{{ tenant.is_active ? 'Yes' : 'No' }}</span>
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
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2 mb-6">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 py-3">Members</h2>
        <DataTable :empty="tenant.members.length === 0" empty-text="No members." :columns="4">
          <thead>
            <tr>
              <th>Email</th>
              <th>Name</th>
              <th>Role</th>
              <th>Default</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in tenant.members" :key="m.user_id">
              <td class="whitespace-nowrap">
                <RouterLink :to="`/admin-portal/users/${m.user_id}`" class="text-indigo-600 dark:text-indigo-400 hover:underline">{{ m.email }}</RouterLink>
              </td>
              <td class="whitespace-nowrap">{{ m.display_name }}</td>
              <td><span class="inline-block px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">{{ m.role }}</span></td>
              <td><span :class="['inline-block w-2 h-2 rounded-full', m.is_default ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600']"></span></td>
            </tr>
          </tbody>
        </DataTable>
      </div>

      <!-- Schema stats -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2">
        <div class="flex flex-wrap items-center justify-between gap-2 py-3">
          <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Schema Stats</h2>
          <span v-if="Object.keys(tenant.table_counts).length > 0" class="text-xs text-gray-400 dark:text-gray-500">
            {{ number(totalRows(tenant.table_counts), 0) }} total rows
          </span>
        </div>
        <DataTable :empty="Object.keys(tenant.table_counts).length === 0" empty-text="No table data available (schema stats require PostgreSQL)." :columns="2" dense>
          <thead>
            <tr>
              <th>Table</th>
              <th class="text-right">Rows</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(count, table) in tenant.table_counts" :key="table">
              <td class="font-mono text-xs">{{ table }}</td>
              <td class="text-right">{{ number(count, 0) }}</td>
            </tr>
          </tbody>
        </DataTable>
      </div>
    </div>
  </div>
</template>
