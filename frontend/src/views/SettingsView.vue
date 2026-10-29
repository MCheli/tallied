<script setup lang="ts">
import { ref, defineAsyncComponent, type Component } from 'vue'

// Each tab is loaded only when first activated, so opening Settings fires the
// loaders of one tab, not of all of them.
type TabKey = 'accounts' | 'income' | 'simplefin' | 'email' | 'import'

const tabs: { key: TabKey; label: string; component: Component }[] = [
  { key: 'accounts', label: 'Accounts', component: defineAsyncComponent(() => import('../components/settings/AccountsTab.vue')) },
  { key: 'income', label: 'Income', component: defineAsyncComponent(() => import('../components/settings/IncomeTab.vue')) },
  { key: 'simplefin', label: 'SimpleFIN', component: defineAsyncComponent(() => import('../components/settings/SimpleFinTab.vue')) },
  { key: 'email', label: 'Email Receipts', component: defineAsyncComponent(() => import('../components/settings/EmailTab.vue')) },
  { key: 'import', label: 'Import History', component: defineAsyncComponent(() => import('../components/settings/ImportHistoryTab.vue')) },
]

const STORAGE_KEY = 'settings-tab'

function readSavedTab(): TabKey {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && tabs.some(t => t.key === saved)) return saved as TabKey
  } catch {
    // storage unavailable: start on the first tab
  }
  return 'accounts'
}

const activeTab = ref<TabKey>(readSavedTab())

function selectTab(key: TabKey) {
  activeTab.value = key
  try {
    localStorage.setItem(STORAGE_KEY, key)
  } catch {
    // storage unavailable: the choice just doesn't persist
  }
}
</script>

<template>
  <div class="min-w-0">
    <h2 class="text-lg font-bold text-gray-900 dark:text-white mb-4">Settings</h2>

    <!-- Tabs: wrap on narrow screens instead of overflowing -->
    <div class="flex flex-wrap gap-2 mb-6" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        role="tab"
        :aria-selected="activeTab === tab.key"
        @click="selectTab(tab.key)"
        :class="[
          'px-3.5 py-2 text-sm rounded-lg transition-colors font-medium whitespace-nowrap',
          activeTab === tab.key
            ? 'bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300'
            : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
        ]"
      >
        {{ tab.label }}
      </button>
    </div>

    <template v-for="tab in tabs" :key="tab.key">
      <component :is="tab.component" v-if="activeTab === tab.key" />
    </template>
  </div>
</template>
