<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../../api/client'
import { useFormatters } from '../../composables/useFormatters'
import type { EmailReceiptItem, ForwardingEmail } from '../../types'

const { currency, dateShort } = useFormatters()

const forwardingEmails = ref<ForwardingEmail[]>([])
const receipts = ref<EmailReceiptItem[]>([])
const newEmail = ref('')
const error = ref('')
const loadError = ref('')
const busy = ref(false)

function describe(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

async function loadAll() {
  loadError.value = ''
  try {
    const [addrs, rcpts] = await Promise.all([api.email.forwardingAddresses(), api.email.receipts(20)])
    forwardingEmails.value = addrs
    receipts.value = rcpts
  } catch (e) {
    loadError.value = 'Failed to load email settings: ' + describe(e)
  }
}

async function addForwardingEmail() {
  error.value = ''
  const email = newEmail.value.trim()
  if (!email) return
  busy.value = true
  try {
    await api.email.addForwardingAddress(email)
    newEmail.value = ''
    forwardingEmails.value = await api.email.forwardingAddresses()
  } catch (e) {
    error.value = describe(e)
  } finally {
    busy.value = false
  }
}

async function removeForwardingEmail(id: number) {
  error.value = ''
  try {
    await api.email.removeForwardingAddress(id)
    forwardingEmails.value = await api.email.forwardingAddresses()
  } catch (e) {
    error.value = 'Failed to remove address: ' + describe(e)
  }
}

onMounted(loadAll)
</script>

<template>
  <div class="min-w-0 space-y-4">
    <!-- Instructions -->
    <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">Email receipt import</h3>
      <p class="text-xs text-gray-500 dark:text-gray-400">
        Forward a receipt (Amazon, PayPal, any merchant) to the household's receipt address and it becomes a transaction.
        The receipt address is configured in Cloudflare Email Routing, not here. Only receipts forwarded
        <span class="font-medium text-gray-700 dark:text-gray-300">from</span> one of the registered addresses below are accepted; anything else is rejected.
      </p>
    </div>

    <div v-if="loadError" class="text-sm text-red-600 dark:text-red-400">{{ loadError }}</div>

    <!-- Registered addresses -->
    <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Registered sender addresses</h3>
      <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">The addresses you forward receipts from.</p>

      <div class="flex flex-col sm:flex-row gap-2 mb-3">
        <input v-model="newEmail" type="email" placeholder="your.email@example.com"
          class="flex-1 min-w-0 px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white placeholder-gray-400"
          @keyup.enter="addForwardingEmail" />
        <button v-demo-lock @click="addForwardingEmail" :disabled="busy || !newEmail.trim()"
          class="px-4 py-2 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
          Add
        </button>
      </div>
      <div v-if="error" class="text-xs text-red-500 mb-3">{{ error }}</div>

      <div v-if="forwardingEmails.length === 0" class="text-xs text-gray-400 py-2">
        No sender addresses registered yet.
      </div>
      <div v-else class="space-y-2">
        <div v-for="addr in forwardingEmails" :key="addr.id"
          class="flex items-center justify-between gap-3 py-2 px-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <span class="text-sm text-gray-900 dark:text-white min-w-0 truncate" :title="addr.email">{{ addr.email }}</span>
          <button v-demo-lock @click="removeForwardingEmail(addr.id)" class="text-xs text-red-500 hover:text-red-700 whitespace-nowrap">Remove</button>
        </div>
      </div>
    </div>

    <!-- Recent receipts -->
    <div class="min-w-0 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
      <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-800">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Recent receipts</h3>
      </div>
      <div v-if="receipts.length === 0" class="px-5 py-8 text-center text-sm text-gray-400">
        No email receipts yet.
      </div>
      <div v-else class="overflow-x-auto min-w-0">
        <table class="w-full min-w-[44rem] text-sm">
          <thead>
            <tr class="border-b border-gray-100 dark:border-gray-800 text-gray-500 dark:text-gray-400">
              <th class="text-left px-5 py-2.5 font-medium">Date</th>
              <th class="text-left px-3 py-2.5 font-medium">From</th>
              <th class="text-left px-3 py-2.5 font-medium">Subject</th>
              <th class="text-left px-3 py-2.5 font-medium">Merchant</th>
              <th class="text-right px-3 py-2.5 font-medium">Amount</th>
              <th class="text-left px-5 py-2.5 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in receipts" :key="r.id" class="border-b border-gray-50 dark:border-gray-800 last:border-0">
              <td class="px-5 py-2.5 text-gray-500 dark:text-gray-400 whitespace-nowrap">{{ dateShort(r.created_at) }}</td>
              <td class="px-3 py-2.5 text-gray-600 dark:text-gray-400 max-w-[150px]"><div class="truncate" :title="r.from_email">{{ r.from_email }}</div></td>
              <td class="px-3 py-2.5 text-gray-900 dark:text-white max-w-[200px]"><div class="truncate" :title="r.subject">{{ r.subject }}</div></td>
              <td class="px-3 py-2.5 text-gray-900 dark:text-white whitespace-nowrap">{{ r.parsed_data?.merchant || '—' }}</td>
              <td class="px-3 py-2.5 text-right text-gray-900 dark:text-white whitespace-nowrap">{{ r.parsed_data?.amount != null ? currency(r.parsed_data.amount) : '—' }}</td>
              <td class="px-5 py-2.5">
                <span :class="[
                  'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
                  r.status === 'parsed' ? 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300' :
                  r.status === 'failed' ? 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300' :
                  'bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300'
                ]" :title="r.error_message || undefined">{{ r.status }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
