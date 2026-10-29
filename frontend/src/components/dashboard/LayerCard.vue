<script setup lang="ts">
import { ref } from 'vue'
import { useFormatters } from '../../composables/useFormatters'
import type { LiquidityLayer } from '../../types'

defineProps<{ layer: LiquidityLayer }>()
const { currency, date } = useFormatters()
const expanded = ref(false)
</script>

<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
    <button
      @click="expanded = !expanded"
      class="w-full flex items-center justify-between gap-3 px-4 sm:px-5 py-3.5 min-h-[44px] hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
      :aria-expanded="expanded"
    >
      <div class="flex items-center gap-3 min-w-0">
        <span class="text-sm font-semibold text-gray-900 dark:text-white truncate">{{ layer.name }}</span>
        <span class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">{{ layer.accounts.length }} {{ layer.accounts.length === 1 ? 'account' : 'accounts' }}</span>
        <span v-if="layer.as_of" class="hidden sm:inline text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">as of {{ date(layer.as_of) }}</span>
      </div>
      <div class="flex items-center gap-3 flex-shrink-0">
        <span class="text-sm font-bold text-gray-900 dark:text-white whitespace-nowrap">{{ currency(layer.total) }}</span>
        <span class="text-gray-400 text-xs transition-transform" :class="{ 'rotate-180': expanded }">&#9660;</span>
      </div>
    </button>
    <div v-if="expanded" class="border-t border-gray-100 dark:border-gray-800">
      <div
        v-for="acct in layer.accounts"
        :key="acct.id"
        class="flex items-center justify-between gap-3 px-4 sm:px-5 py-2.5 text-sm"
      >
        <div class="min-w-0">
          <span class="text-gray-700 dark:text-gray-300 truncate block" :title="acct.name">{{ acct.name }}</span>
          <span class="text-xs text-gray-400 dark:text-gray-500">
            {{ acct.balance_date ? `as of ${date(acct.balance_date)}` : '' }}
            <span v-if="acct.include_in_nw === false" class="ml-1 inline-block px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-[10px] uppercase tracking-wide">not in net worth</span>
          </span>
        </div>
        <span class="font-medium text-gray-900 dark:text-white whitespace-nowrap" :class="{ 'text-gray-400 dark:text-gray-500': acct.include_in_nw === false }">{{ currency(acct.balance) }}</span>
      </div>
    </div>
  </div>
</template>
