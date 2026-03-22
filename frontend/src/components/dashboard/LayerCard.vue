<script setup lang="ts">
import { ref } from 'vue'
import { useFormatters } from '../../composables/useFormatters'
import type { LiquidityLayer } from '../../types'

defineProps<{ layer: LiquidityLayer }>()
const { currency } = useFormatters()
const expanded = ref(false)
</script>

<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
    <button
      @click="expanded = !expanded"
      class="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
    >
      <div class="flex items-center gap-3">
        <span class="text-sm font-semibold text-gray-900 dark:text-white">{{ layer.name }}</span>
        <span class="text-xs text-gray-500 dark:text-gray-400">{{ layer.accounts.length }} {{ layer.accounts.length === 1 ? 'account' : 'accounts' }}</span>
      </div>
      <div class="flex items-center gap-3">
        <span class="text-sm font-bold text-gray-900 dark:text-white">{{ currency(layer.total) }}</span>
        <span class="text-gray-400 text-xs transition-transform" :class="{ 'rotate-180': expanded }">&#9660;</span>
      </div>
    </button>
    <div v-if="expanded" class="border-t border-gray-100 dark:border-gray-800">
      <div
        v-for="acct in layer.accounts"
        :key="acct.id"
        class="flex items-center justify-between px-5 py-3 text-sm"
      >
        <span class="text-gray-700 dark:text-gray-300">{{ acct.name }}</span>
        <span class="font-medium text-gray-900 dark:text-white">{{ currency(acct.balance) }}</span>
      </div>
    </div>
  </div>
</template>
