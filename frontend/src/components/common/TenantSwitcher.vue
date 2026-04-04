<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { Users } from 'lucide-vue-next'

const props = withDefaults(defineProps<{ collapsed?: boolean }>(), { collapsed: false })

const auth = useAuthStore()
const open = ref(false)
const switching = ref(false)

async function switchTo(tenantId: number) {
  if (tenantId === auth.user?.current_tenant?.id) {
    open.value = false
    return
  }
  switching.value = true
  await auth.selectTenant(tenantId)
  switching.value = false
  open.value = false
}
</script>

<template>
  <div v-if="auth.user?.tenants && auth.user.tenants.length > 1" class="relative px-3 py-2 border-b border-gray-100 dark:border-gray-800">
    <button
      @click="open = !open"
      :title="collapsed ? auth.user.current_tenant?.display_name : undefined"
      :aria-label="collapsed ? `Switch tenant (${auth.user.current_tenant?.display_name})` : undefined"
      :class="[
        'w-full flex items-center rounded-lg text-xs font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors',
        collapsed ? 'justify-center px-0 py-2' : 'justify-between gap-2 px-2 py-1.5',
      ]"
    >
      <Users v-if="collapsed" class="w-4 h-4 flex-shrink-0" />
      <template v-else>
        <span class="truncate">{{ auth.user.current_tenant?.display_name }}</span>
        <svg
          class="w-3 h-3 text-gray-400 flex-shrink-0 transition-transform"
          :class="{ 'rotate-180': open }"
          viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
        >
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </template>
    </button>

    <!-- Dropdown -->
    <div
      v-if="open"
      class="absolute left-3 right-3 bottom-full mb-1 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 py-1"
    >
      <button
        v-for="t in auth.user.tenants"
        :key="t.id"
        @click="switchTo(t.id)"
        :disabled="switching"
        :class="[
          'w-full text-left px-3 py-1.5 text-xs transition-colors',
          t.id === auth.user.current_tenant?.id
            ? 'text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/40 font-medium'
            : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800'
        ]"
      >
        {{ t.display_name }}
      </button>
    </div>
  </div>

  <!-- Single tenant: just show the name (hide when collapsed since there's nothing to switch) -->
  <div v-else-if="auth.user?.current_tenant && !collapsed" class="px-3 py-1.5 border-b border-gray-100 dark:border-gray-800">
    <span class="text-[10px] text-gray-400 dark:text-gray-500 truncate block">{{ auth.user.current_tenant.display_name }}</span>
  </div>
</template>
