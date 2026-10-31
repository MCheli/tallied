<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../../api/client'
import type { SimpleFinAccountConfig, SimpleFinAccountType, SimpleFinStatus } from '../../types'

const status = ref<SimpleFinStatus>({ connected: false })
const accounts = ref<SimpleFinAccountConfig[]>([])
const accountTypes = ref<SimpleFinAccountType[]>([])
const loading = ref(false)

const setupToken = ref('')
const connecting = ref(false)
const syncing = ref(false)
const message = ref('')
const isError = ref(false)

const showRefresh = ref(false)
const refreshToken = ref('')
const refreshing = ref(false)
const rowError = ref<Record<number, string>>({})

function say(text: string, error = false) {
  message.value = text
  isError.value = error
}

function describe(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

async function loadStatus() {
  try {
    status.value = await api.simplefin.status()
  } catch (e) {
    say('Failed to load SimpleFIN status: ' + describe(e), true)
  }
}

async function loadAccounts() {
  loading.value = true
  try {
    const [cfgs, types] = await Promise.all([api.simplefin.accounts(), api.simplefin.accountTypes()])
    accounts.value = cfgs
    accountTypes.value = types
  } catch (e) {
    say('Failed to load account configuration: ' + describe(e), true)
  }
  loading.value = false
}

function groupFor(accountType: string | null): string {
  return accountTypes.value.find(t => t.account_type === accountType)?.display_group ?? '—'
}

async function connect() {
  const token = setupToken.value.trim()
  if (!token) return
  connecting.value = true
  say('Claiming setup token...')
  try {
    const data = await api.simplefin.connect(token)
    const warn = data.warnings.length ? ` Warnings: ${data.warnings.join('; ')}` : ''
    say(`Connected. Found ${data.accounts_found} account${data.accounts_found === 1 ? '' : 's'}; check each one's type below.${warn}`)
    setupToken.value = ''
    await loadStatus()
    await loadAccounts()
  } catch (e) {
    say('Error: ' + describe(e), true)
  } finally {
    connecting.value = false
  }
}

async function updateConfig(cfg: SimpleFinAccountConfig, data: { sync_balances?: boolean; sync_transactions?: boolean; account_type?: string }) {
  delete rowError.value[cfg.id]
  try {
    const updated = await api.simplefin.updateAccount(cfg.id, data)
    Object.assign(cfg, updated)
  } catch (e) {
    rowError.value[cfg.id] = describe(e)
    await loadAccounts()
  }
}

function onToggle(cfg: SimpleFinAccountConfig, field: 'sync_balances' | 'sync_transactions', e: Event) {
  updateConfig(cfg, { [field]: (e.target as HTMLInputElement).checked })
}

function onTypeChange(cfg: SimpleFinAccountConfig, e: Event) {
  updateConfig(cfg, { account_type: (e.target as HTMLSelectElement).value })
}

async function syncAll() {
  syncing.value = true
  say('Queuing SimpleFIN sync...')
  try {
    const started = await api.simplefin.sync()
    if (started.status === 'skipped') {
      say(started.detail || 'No SimpleFIN connection.', true)
      return
    }
    say('Syncing: fetching accounts and recent transactions...')
    const POLL = 2000
    const CEILING = 10 * 60 * 1000
    const begun = Date.now()
    let last: Awaited<ReturnType<typeof api.simplefin.syncStatus>> | null = null
    while (Date.now() - begun < CEILING) {
      await new Promise(r => setTimeout(r, POLL))
      try {
        last = await api.simplefin.syncStatus()
      } catch {
        continue
      }
      if (last.status !== 'running') break
    }
    if (!last || last.status === 'running') {
      say('Sync is still running in the background. Check back in a few minutes.')
    } else if (last.status === 'failed') {
      say(`Sync failed: ${last.error || 'unknown error'}`, true)
    } else {
      say(`Done: ${last.balances_synced ?? 0} balances, ${last.txn_added ?? 0} transactions added, ${last.txn_updated ?? 0} updated.`)
    }
    await loadStatus()
  } catch (e) {
    say('Sync error: ' + describe(e), true)
  } finally {
    syncing.value = false
  }
}

function openRefresh() {
  showRefresh.value = true
  refreshToken.value = ''
  say('')
}

function cancelRefresh() {
  showRefresh.value = false
  refreshToken.value = ''
}

async function refreshCredentials() {
  const token = refreshToken.value.trim()
  if (!token) return
  refreshing.value = true
  say('Refreshing SimpleFIN credentials...')
  try {
    await api.simplefin.refreshCredentials(token)
    say('Credentials refreshed. Account settings preserved.')
    cancelRefresh()
    await loadStatus()
  } catch (e) {
    say('Error: ' + describe(e), true)
  } finally {
    refreshing.value = false
  }
}

async function disconnect() {
  try {
    await api.simplefin.disconnect()
    status.value = { connected: false }
    accounts.value = []
    say('Disconnected. Synced accounts and their history stay in Tallied.')
  } catch (e) {
    say('Failed to disconnect: ' + describe(e), true)
  }
}

onMounted(async () => {
  await loadStatus()
  if (status.value.connected) await loadAccounts()
})

const selectClass = 'px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white'
</script>

<template>
  <div class="min-w-0 space-y-4">
    <div v-if="!status.connected" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">Connect SimpleFIN Bridge</h3>
      <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">
        Get a setup token from
        <a href="https://beta-bridge.simplefin.org/" target="_blank" rel="noopener" class="text-indigo-600 dark:text-indigo-400 hover:underline">beta-bridge.simplefin.org</a>
        and paste it below. Tokens are single-use; the access URL it yields is stored encrypted.
      </p>
      <div class="space-y-2">
        <textarea v-model="setupToken" placeholder="Paste base64 setup token here" rows="3"
          class="w-full px-3 py-2 text-xs font-mono border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"></textarea>
        <div class="flex justify-end">
          <button v-demo-lock @click="connect" :disabled="connecting || !setupToken.trim()"
            class="px-4 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
            {{ connecting ? 'Connecting...' : 'Connect' }}
          </button>
        </div>
        <div v-if="message" class="text-xs" :class="isError ? 'text-red-500' : 'text-green-600 dark:text-green-400'">{{ message }}</div>
      </div>
    </div>

    <template v-else>
      <!-- Connected status + actions -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="min-w-0">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">SimpleFIN connected</h3>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
              <span v-if="status.last_synced_at">Last synced {{ new Date(status.last_synced_at).toLocaleString() }}</span>
              <span v-else>Never synced</span>
              <span> · runs every 12 hours</span>
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <button v-demo-lock @click="syncAll" :disabled="syncing"
              class="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
              {{ syncing ? 'Syncing...' : 'Sync now' }}
            </button>
            <button v-demo-lock @click="openRefresh" :disabled="refreshing"
              class="px-3 py-1.5 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 rounded-lg disabled:opacity-50">
              Refresh credentials
            </button>
            <button v-demo-lock @click="disconnect"
              class="px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-lg">
              Disconnect
            </button>
          </div>
        </div>
        <div v-if="message" class="mt-3 text-xs" :class="isError ? 'text-red-500' : 'text-green-600 dark:text-green-400'">{{ message }}</div>

        <div v-if="showRefresh" class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800 space-y-2">
          <h4 class="text-xs font-semibold text-gray-700 dark:text-gray-300">Refresh access URL</h4>
          <p class="text-xs text-gray-400 dark:text-gray-500">Paste a fresh setup token. Account settings are preserved.</p>
          <textarea v-model="refreshToken" placeholder="New setup token" rows="3"
            class="w-full px-3 py-2 text-xs font-mono border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"></textarea>
          <div class="flex items-center justify-end gap-2">
            <button @click="cancelRefresh" class="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">Cancel</button>
            <button v-demo-lock @click="refreshCredentials" :disabled="refreshing || !refreshToken.trim()"
              class="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
              {{ refreshing ? 'Refreshing...' : 'Refresh' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Account configuration -->
      <div class="min-w-0 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-800">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Account sync configuration</h3>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            SimpleFIN returns balances and about 45 days of transactions per account. The type decides which layer a new account lands in; it is used when the account is first created in Tallied.
          </p>
        </div>
        <div v-if="loading" class="px-5 py-4 text-xs text-gray-400">Loading...</div>
        <div v-else-if="accounts.length === 0" class="px-5 py-4 text-xs text-gray-400">No accounts.</div>
        <div v-else class="overflow-x-auto min-w-0">
          <table class="w-full min-w-[40rem] text-xs">
            <thead class="bg-gray-50 dark:bg-gray-950/50 border-b border-gray-100 dark:border-gray-800">
              <tr>
                <th class="text-left px-5 py-2 font-medium text-gray-600 dark:text-gray-400">Account</th>
                <th class="text-left px-3 py-2 font-medium text-gray-600 dark:text-gray-400">Institution</th>
                <th class="text-left px-3 py-2 font-medium text-gray-600 dark:text-gray-400">Type</th>
                <th class="text-left px-3 py-2 font-medium text-gray-600 dark:text-gray-400">Group</th>
                <th class="text-center px-3 py-2 font-medium text-gray-600 dark:text-gray-400">Balances</th>
                <th class="text-center px-3 py-2 font-medium text-gray-600 dark:text-gray-400">Transactions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
              <tr v-for="cfg in accounts" :key="cfg.id">
                <td class="px-5 py-2 text-gray-900 dark:text-white max-w-[14rem]">
                  <div class="min-w-0 truncate" :title="cfg.account_name">{{ cfg.account_name }}</div>
                  <div v-if="rowError[cfg.id]" class="text-red-500 text-[11px] mt-0.5">{{ rowError[cfg.id] }}</div>
                </td>
                <td class="px-3 py-2 text-gray-500 dark:text-gray-400 whitespace-nowrap">{{ cfg.institution || '—' }}</td>
                <td class="px-3 py-2">
                  <select :value="cfg.account_type ?? ''" @change="onTypeChange(cfg, $event)" :class="selectClass">
                    <option v-if="!cfg.account_type" value="" disabled>choose</option>
                    <option v-for="t in accountTypes" :key="t.account_type" :value="t.account_type">{{ t.account_type }}</option>
                  </select>
                </td>
                <td class="px-3 py-2 text-gray-500 dark:text-gray-400 whitespace-nowrap">{{ groupFor(cfg.account_type) }}</td>
                <td class="px-3 py-2 text-center">
                  <input type="checkbox" :checked="cfg.sync_balances" @change="onToggle(cfg, 'sync_balances', $event)" class="rounded text-indigo-600" />
                </td>
                <td class="px-3 py-2 text-center">
                  <input type="checkbox" :checked="cfg.sync_transactions" @change="onToggle(cfg, 'sync_transactions', $event)" class="rounded text-indigo-600" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
