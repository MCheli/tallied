<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import PageHeader from '../components/common/PageHeader.vue'
import MetricCard from '../components/common/MetricCard.vue'
import DataTable from '../components/common/DataTable.vue'
import { useThemeStore } from '../stores/theme'
import { useFormatters } from '../composables/useFormatters'
import { apiErrorMessage } from '../composables/useApiError'
import { api } from '../api/client'
import type { ApiKey, UsageSummary, Webhook, WebhookTestResult } from '../types'

// The snippets are copied into a terminal, so they need the full origin, not a path relative to this page.
const API = import.meta.env.VITE_API_URL || (typeof window !== 'undefined' ? window.location.origin : '')
const { number, date } = useFormatters()

// ── Tabs ─────────────────────────────────────────────────────────────────────
type Tab = 'keys' | 'webhooks' | 'docs'
const activeTab = ref<Tab>('keys')
const TABS: { key: Tab; label: string }[] = [
  { key: 'keys', label: 'Keys & Usage' },
  { key: 'webhooks', label: 'Webhooks' },
  { key: 'docs', label: 'API Reference' },
]

// ── API Keys ─────────────────────────────────────────────────────────────────
const keys = ref<ApiKey[]>([])
const loading = ref(true)
const keysError = ref('')

const showCreate = ref(false)
const newName = ref('')
const newPermissions = ref('read')
const creating = ref(false)

const createdKey = ref<string | null>(null)
const copied = ref(false)

async function loadKeys() {
  loading.value = true
  keysError.value = ''
  try {
    keys.value = await api.keys.list()
  } catch (e) {
    keysError.value = apiErrorMessage(e, 'Could not load API keys')
  }
  loading.value = false
}

async function createKey() {
  if (!newName.value.trim()) return
  creating.value = true
  keysError.value = ''
  try {
    const data = await api.keys.create(newName.value.trim(), newPermissions.value)
    createdKey.value = data.key
    newName.value = ''
    showCreate.value = false
    await loadKeys()
  } catch (e) {
    keysError.value = apiErrorMessage(e, 'Could not create the key')
  }
  creating.value = false
}

async function revokeKey(id: number) {
  keysError.value = ''
  try {
    await api.keys.revoke(id)
  } catch (e) {
    keysError.value = apiErrorMessage(e, 'Could not revoke the key')
  }
  await loadKeys()
}

async function copyText(text: string, flag: typeof copied) {
  try {
    await navigator.clipboard.writeText(text)
    flag.value = true
    setTimeout(() => (flag.value = false), 2000)
  } catch {
    // Clipboard refused (older webviews): the value is selectable in the box next to the button.
  }
}

function copyKey() {
  if (createdKey.value) copyText(createdKey.value, copied)
}

function dismissCreatedKey() {
  createdKey.value = null
  copied.value = false
}

function fmtDate(iso: string | null): string {
  return iso ? date(iso) : 'Never'
}

// ── Usage stats ──────────────────────────────────────────────────────────────
const usage = ref<UsageSummary | null>(null)
const usageError = ref('')

const keyUsage24h = computed(() => {
  const map = new Map<number, number>()
  if (usage.value) {
    for (const k of usage.value.per_key) map.set(k.key_id, k.requests_last_24h)
  }
  return map
})

async function loadUsage() {
  usageError.value = ''
  try {
    usage.value = await api.keys.usage()
  } catch (e) {
    usageError.value = apiErrorMessage(e, 'Could not load usage')
  }
}

// ── Webhooks ─────────────────────────────────────────────────────────────────
const WEBHOOK_EVENT_TYPES: { name: string; when: string }[] = [
  { name: 'transaction.created', when: 'after a sync adds transactions' },
  { name: 'balance.updated', when: 'after a sync records balances' },
  { name: 'import.completed', when: 'when a document import is confirmed' },
  { name: 'account.created', when: 'reserved; not emitted yet' },
]

const webhooks = ref<Webhook[]>([])
const webhooksLoading = ref(true)
const webhooksError = ref('')

const showCreateWebhook = ref(false)
const newWebhookUrl = ref('')
const newWebhookEvents = ref<string[]>([])
const creatingWebhook = ref(false)

const createdSecret = ref<string | null>(null)
const secretCopied = ref(false)

const testingId = ref<number | null>(null)
const testResult = ref<WebhookTestResult | null>(null)

async function loadWebhooks() {
  webhooksLoading.value = true
  webhooksError.value = ''
  try {
    webhooks.value = await api.webhooks.list()
  } catch (e) {
    webhooksError.value = apiErrorMessage(e, 'Could not load webhooks')
  }
  webhooksLoading.value = false
}

async function createWebhook() {
  if (!newWebhookUrl.value.trim() || newWebhookEvents.value.length === 0) return
  creatingWebhook.value = true
  webhooksError.value = ''
  try {
    const data = await api.webhooks.create(newWebhookUrl.value.trim(), newWebhookEvents.value)
    createdSecret.value = data.secret
    newWebhookUrl.value = ''
    newWebhookEvents.value = []
    showCreateWebhook.value = false
    await loadWebhooks()
  } catch (e) {
    webhooksError.value = apiErrorMessage(e, 'Could not create the webhook')
  }
  creatingWebhook.value = false
}

async function deleteWebhook(id: number) {
  webhooksError.value = ''
  try {
    await api.webhooks.remove(id)
  } catch (e) {
    webhooksError.value = apiErrorMessage(e, 'Could not delete the webhook')
  }
  await loadWebhooks()
}

async function toggleWebhook(wh: Webhook) {
  webhooksError.value = ''
  try {
    await api.webhooks.update(wh.id, { is_active: !wh.is_active })
  } catch (e) {
    webhooksError.value = apiErrorMessage(e, 'Could not update the webhook')
  }
  await loadWebhooks()
}

async function testWebhook(id: number) {
  testingId.value = id
  testResult.value = null
  try {
    testResult.value = await api.webhooks.test(id)
  } catch (e) {
    testResult.value = { success: false, error: apiErrorMessage(e, 'Request failed') }
  }
  setTimeout(() => {
    if (testingId.value === id) {
      testingId.value = null
      testResult.value = null
    }
  }, 4000)
}

function copySecret() {
  if (createdSecret.value) copyText(createdSecret.value, secretCopied)
}

function dismissCreatedSecret() {
  createdSecret.value = null
  secretCopied.value = false
}

function toggleEvent(event: string) {
  const idx = newWebhookEvents.value.indexOf(event)
  if (idx >= 0) newWebhookEvents.value.splice(idx, 1)
  else newWebhookEvents.value.push(event)
}

// ── Scalar API Docs ──────────────────────────────────────────────────────────
const isDark = computed(() => useThemeStore().dark)
const scalarUrl = computed(() => `${API}/api/v1/scalar?dark=${isDark.value ? '1' : '0'}`)

onMounted(() => {
  loadKeys()
  loadUsage()
  loadWebhooks()
})
</script>

<template>
  <div class="min-w-0">
    <PageHeader
      title="API"
      subtitle="Programmatic access to the household's data"
      tooltip="<strong>API Access</strong><br>Create API keys for programmatic access to your financial data. Authenticate with the <code>X-API-Key</code> header. A read key can only call GET endpoints; a write key can change data; admin routes need an admin key."
    >
      <template #below>
        <div class="flex flex-wrap gap-1">
          <button
            v-for="tab in TABS"
            :key="tab.key"
            @click="activeTab = tab.key"
            :aria-pressed="activeTab === tab.key"
            :class="[
              'min-h-10 px-4 py-2 rounded-lg text-xs font-medium transition-colors',
              activeTab === tab.key
                ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
            ]"
          >{{ tab.label }}</button>
        </div>
      </template>
    </PageHeader>

    <!-- ═══ Keys & Usage Tab ═══ -->
    <div v-show="activeTab === 'keys'">
      <!-- Newly created key banner -->
      <div v-if="createdKey" class="mb-6 bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 rounded-xl p-5">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-sm font-semibold text-green-800 dark:text-green-300">API Key Created</h3>
          <button @click="dismissCreatedKey" class="min-h-10 px-2 text-green-500 hover:text-green-700 text-xs">Dismiss</button>
        </div>
        <p class="text-xs text-green-700 dark:text-green-400 mb-3">Copy this key now. It is not shown again.</p>
        <div class="flex flex-wrap items-center gap-2">
          <code class="flex-1 min-w-0 px-3 py-2 text-xs font-mono bg-white dark:bg-gray-900 border border-green-200 dark:border-green-700 rounded-lg text-gray-800 dark:text-gray-200 select-all break-all">{{ createdKey }}</code>
          <button @click="copyKey"
            class="min-h-10 px-3 py-2 text-xs font-medium rounded-lg transition-colors"
            :class="copied ? 'bg-green-600 text-white' : 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 hover:bg-green-200 dark:hover:bg-green-800'"
          >{{ copied ? 'Copied' : 'Copy' }}</button>
        </div>
      </div>

      <!-- Usage tiles: every /api/v1 request by this tenant, cookie or key -->
      <p v-if="usageError" class="mb-3 text-xs text-red-600 dark:text-red-400">{{ usageError }}</p>
      <div v-if="usage" class="mb-6 grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard label="Today" :value="number(usage.total_requests_today, 0)" subtitle="requests"
          info="Requests to /api/v1 by this tenant since midnight, from the browser session and from API keys alike. Per-key counts are on each key below." />
        <MetricCard label="Last hour" :value="number(usage.requests_last_hour, 0)" subtitle="requests" />
        <MetricCard label="All time" :value="number(usage.total_requests_all_time, 0)" subtitle="requests" />
        <MetricCard label="Avg latency" :value="`${number(usage.avg_latency_ms, 0)} ms`" subtitle="server time per request" />
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- API Keys Card -->
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden min-w-0 lg:self-start">
          <div class="flex flex-wrap items-center justify-between gap-2 px-5 py-4 border-b border-gray-100 dark:border-gray-800">
            <div class="min-w-0">
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white">API Keys</h2>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Manage programmatic access to your data</p>
            </div>
            <button
              @click="showCreate = !showCreate"
              class="min-h-10 px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
            >{{ showCreate ? 'Cancel' : 'New Key' }}</button>
          </div>

          <p v-if="keysError" class="px-5 py-2 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30">{{ keysError }}</p>

          <!-- Create form -->
          <div v-if="showCreate" class="px-5 py-4 border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/30">
            <div class="space-y-3">
              <div>
                <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
                <input v-model="newName" type="text" placeholder="e.g., jupyter-notebook"
                  class="w-full px-3 py-2 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
              </div>
              <div>
                <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Permissions</label>
                <select v-model="newPermissions"
                  class="w-full px-3 py-2 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500">
                  <option value="read">Read only (GET endpoints)</option>
                  <option value="write">Read + Write</option>
                  <option value="admin">Admin (also the platform routes)</option>
                </select>
              </div>
              <button @click="createKey" :disabled="creating || !newName.trim()"
                class="w-full min-h-10 px-3 py-2 text-xs font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors">
                {{ creating ? 'Creating...' : 'Create API Key' }}
              </button>
            </div>
          </div>

          <!-- Keys list -->
          <div class="divide-y divide-gray-50 dark:divide-gray-800">
            <div v-if="loading" class="px-5 py-8 text-center">
              <div class="animate-spin rounded-full h-5 w-5 border-b-2 border-indigo-500 mx-auto"></div>
            </div>
            <div v-else-if="keys.length === 0 && !showCreate" class="px-5 py-8 text-center">
              <p class="text-sm text-gray-400 dark:text-gray-500">No API keys yet.</p>
              <p class="text-xs text-gray-300 dark:text-gray-600 mt-1">Create one to access your data programmatically.</p>
            </div>
            <div v-for="key in keys" :key="key.id" class="px-5 py-3 flex items-center justify-between gap-3 min-w-0">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="text-xs font-medium text-gray-900 dark:text-white truncate">{{ key.name }}</span>
                  <span :class="[
                    'text-[10px] px-1.5 py-0.5 rounded-full font-medium',
                    key.is_active
                      ? 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-400'
                      : 'bg-gray-100 dark:bg-gray-800 text-gray-400'
                  ]">{{ key.is_active ? key.permissions : 'revoked' }}</span>
                  <span v-if="keyUsage24h.has(key.id)"
                    class="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
                    {{ number(keyUsage24h.get(key.id) ?? 0, 0) }} req/24h
                  </span>
                </div>
                <div class="text-[11px] text-gray-400 dark:text-gray-500 mt-0.5 font-mono truncate">
                  {{ key.key_prefix }}...
                  <span class="ml-2 font-sans">Created {{ fmtDate(key.created_at) }}</span>
                  <span v-if="key.last_used" class="ml-2 font-sans">Last used {{ fmtDate(key.last_used) }}</span>
                </div>
              </div>
              <button v-if="key.is_active" @click="revokeKey(key.id)"
                class="min-h-10 px-2 text-xs text-red-500 hover:text-red-600 font-medium transition-colors shrink-0">
                Revoke
              </button>
            </div>
          </div>
        </div>

        <!-- Right column: Top Endpoints + Quick Start -->
        <div class="space-y-4 min-w-0">
          <!-- Top Endpoints -->
          <div v-if="usage && usage.top_endpoints.length > 0" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden px-4">
            <div class="py-4 border-b border-gray-100 dark:border-gray-800">
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white">Most-Used Endpoints</h2>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">All time, every caller</p>
            </div>
            <DataTable dense :columns="3">
              <thead>
                <tr>
                  <th>Method</th>
                  <th>Path</th>
                  <th class="text-right">Requests</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="ep in usage.top_endpoints" :key="ep.method + ep.path">
                  <td>
                    <span :class="[
                      'text-[10px] font-mono font-bold px-1.5 py-0.5 rounded',
                      ep.method === 'GET' ? 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400' :
                      ep.method === 'POST' ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400' :
                      ep.method === 'DELETE' ? 'bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400' :
                      'bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
                    ]">{{ ep.method }}</span>
                  </td>
                  <td class="font-mono text-xs whitespace-nowrap">{{ ep.path }}</td>
                  <td class="text-right text-gray-900 dark:text-white font-medium">{{ number(ep.count, 0) }}</td>
                </tr>
              </tbody>
            </DataTable>
          </div>

          <!-- Quick Start -->
          <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 min-w-0">
            <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Quick Start</h2>
            <div class="space-y-3">
              <div>
                <p class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">curl</p>
                <pre class="text-[11px] font-mono bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-lg p-3 overflow-x-auto text-gray-700 dark:text-gray-300">curl -H "X-API-Key: YOUR_KEY" \
  {{ API }}/api/v1/snapshot</pre>
              </div>
              <div>
                <p class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Python</p>
                <pre class="text-[11px] font-mono bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-lg p-3 overflow-x-auto text-gray-700 dark:text-gray-300">import requests

API_KEY = "YOUR_KEY"
BASE = "{{ API }}/api/v1"

r = requests.get(f"{BASE}/snapshot",
    headers={"X-API-Key": API_KEY})
data = r.json()
print(f"Net Worth: ${data['net_worth']:,.0f}")</pre>
              </div>
              <div>
                <p class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">JavaScript</p>
                <pre class="text-[11px] font-mono bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-lg p-3 overflow-x-auto text-gray-700 dark:text-gray-300">const res = await fetch("{{ API }}/api/v1/snapshot", {
  headers: { "X-API-Key": "YOUR_KEY" }
});
const data = await res.json();</pre>
              </div>
            </div>
          </div>

          <!-- Base URL -->
          <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 min-w-0">
            <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">Base URL</h2>
            <code class="text-xs font-mono px-3 py-2 bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-lg block text-gray-700 dark:text-gray-300 break-all">{{ API }}/api/v1</code>
            <p class="text-[11px] text-gray-400 dark:text-gray-500 mt-2">All endpoints require authentication via the <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded">X-API-Key</code> header or the session cookie.</p>
          </div>

          <!-- Rate Limits -->
          <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 min-w-0">
            <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">Rate Limits</h2>
            <p class="text-xs text-gray-600 dark:text-gray-400">Each API key (and each signed-in user) is limited to <strong class="text-gray-900 dark:text-white">1,000 requests per hour</strong> (sliding window, counted per server process). Every response includes headers to track your usage:</p>
            <div class="mt-3 space-y-1">
              <div class="flex flex-wrap items-center gap-2 text-[11px] font-mono text-gray-600 dark:text-gray-400">
                <code class="bg-gray-50 dark:bg-gray-950 px-2 py-0.5 rounded border border-gray-200 dark:border-gray-800">X-RateLimit-Limit</code>
                <span class="text-gray-400 dark:text-gray-500">max requests per hour</span>
              </div>
              <div class="flex flex-wrap items-center gap-2 text-[11px] font-mono text-gray-600 dark:text-gray-400">
                <code class="bg-gray-50 dark:bg-gray-950 px-2 py-0.5 rounded border border-gray-200 dark:border-gray-800">X-RateLimit-Remaining</code>
                <span class="text-gray-400 dark:text-gray-500">requests remaining</span>
              </div>
              <div class="flex flex-wrap items-center gap-2 text-[11px] font-mono text-gray-600 dark:text-gray-400">
                <code class="bg-gray-50 dark:bg-gray-950 px-2 py-0.5 rounded border border-gray-200 dark:border-gray-800">X-RateLimit-Reset</code>
                <span class="text-gray-400 dark:text-gray-500">window reset (unix timestamp)</span>
              </div>
            </div>
            <p class="text-[11px] text-gray-400 dark:text-gray-500 mt-3">When the limit is exceeded, the API returns <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded">429 Too Many Requests</code> with a <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded">Retry-After</code> header.</p>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ Webhooks Tab ═══ -->
    <div v-show="activeTab === 'webhooks'">
      <!-- Newly created secret banner -->
      <div v-if="createdSecret" class="mb-6 bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 rounded-xl p-5">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-sm font-semibold text-green-800 dark:text-green-300">Webhook Created</h3>
          <button @click="dismissCreatedSecret" class="min-h-10 px-2 text-green-500 hover:text-green-700 text-xs">Dismiss</button>
        </div>
        <p class="text-xs text-green-700 dark:text-green-400 mb-3">Copy the signing secret now. It is not shown again. Use it to verify webhook signatures.</p>
        <div class="flex flex-wrap items-center gap-2">
          <code class="flex-1 min-w-0 px-3 py-2 text-xs font-mono bg-white dark:bg-gray-900 border border-green-200 dark:border-green-700 rounded-lg text-gray-800 dark:text-gray-200 select-all break-all">{{ createdSecret }}</code>
          <button @click="copySecret"
            class="min-h-10 px-3 py-2 text-xs font-medium rounded-lg transition-colors"
            :class="secretCopied ? 'bg-green-600 text-white' : 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 hover:bg-green-200 dark:hover:bg-green-800'"
          >{{ secretCopied ? 'Copied' : 'Copy' }}</button>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Webhooks list -->
        <div class="lg:col-span-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden min-w-0">
          <div class="flex flex-wrap items-center justify-between gap-2 px-5 py-4 border-b border-gray-100 dark:border-gray-800">
            <div class="min-w-0">
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white">Webhook Subscriptions</h2>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">An HTTP POST to your URL when a sync completes or an import is confirmed</p>
            </div>
            <button
              @click="showCreateWebhook = !showCreateWebhook"
              class="min-h-10 px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
            >{{ showCreateWebhook ? 'Cancel' : 'New Webhook' }}</button>
          </div>

          <p v-if="webhooksError" class="px-5 py-2 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30">{{ webhooksError }}</p>

          <!-- Create form -->
          <div v-if="showCreateWebhook" class="px-5 py-4 border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/30">
            <div class="space-y-3">
              <div>
                <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Payload URL</label>
                <input v-model="newWebhookUrl" type="url" placeholder="https://example.com/webhook"
                  class="w-full px-3 py-2 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
                <p class="text-[11px] text-gray-400 dark:text-gray-500 mt-1">Public http(s) hosts only; private and local addresses are refused.</p>
              </div>
              <div>
                <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Events</label>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <label v-for="evt in WEBHOOK_EVENT_TYPES" :key="evt.name"
                    class="flex items-center gap-2 px-3 py-2 min-h-10 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors"
                    :class="newWebhookEvents.includes(evt.name) ? 'border-indigo-400 dark:border-indigo-600 bg-indigo-50 dark:bg-indigo-950/30' : ''">
                    <input type="checkbox" :checked="newWebhookEvents.includes(evt.name)" @change="toggleEvent(evt.name)"
                      class="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500" />
                    <span class="font-mono text-gray-700 dark:text-gray-300">{{ evt.name }}</span>
                  </label>
                </div>
              </div>
              <button @click="createWebhook" :disabled="creatingWebhook || !newWebhookUrl.trim() || newWebhookEvents.length === 0"
                class="w-full min-h-10 px-3 py-2 text-xs font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors">
                {{ creatingWebhook ? 'Creating...' : 'Create Webhook' }}
              </button>
            </div>
          </div>

          <!-- Webhooks list -->
          <div class="divide-y divide-gray-50 dark:divide-gray-800">
            <div v-if="webhooksLoading" class="px-5 py-8 text-center">
              <div class="animate-spin rounded-full h-5 w-5 border-b-2 border-indigo-500 mx-auto"></div>
            </div>
            <div v-else-if="webhooks.length === 0 && !showCreateWebhook" class="px-5 py-8 text-center">
              <p class="text-sm text-gray-400 dark:text-gray-500">No webhooks yet.</p>
              <p class="text-xs text-gray-300 dark:text-gray-600 mt-1">Create one to receive event notifications.</p>
            </div>
            <div v-for="wh in webhooks" :key="wh.id" class="px-5 py-4 min-w-0">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="flex-1 min-w-0">
                  <div class="flex flex-wrap items-center gap-2 mb-1 min-w-0">
                    <span class="text-xs font-mono text-gray-900 dark:text-white truncate max-w-full">{{ wh.url }}</span>
                    <span :class="[
                      'text-[10px] px-1.5 py-0.5 rounded-full font-medium whitespace-nowrap',
                      wh.is_active
                        ? 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-400'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-400'
                    ]">{{ wh.is_active ? 'active' : 'inactive' }}</span>
                    <span v-if="wh.failure_count > 0"
                      class="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-400 whitespace-nowrap">
                      {{ wh.failure_count }} failures
                    </span>
                  </div>
                  <div class="flex flex-wrap gap-1 mb-1">
                    <span v-for="evt in wh.events" :key="evt"
                      class="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 font-mono">
                      {{ evt }}
                    </span>
                  </div>
                  <div class="text-[11px] text-gray-400 dark:text-gray-500">
                    Created {{ fmtDate(wh.created_at) }}
                    <span class="ml-2">Last delivery: {{ fmtDate(wh.last_delivery) }}</span>
                  </div>
                </div>
                <div class="flex items-center gap-1 shrink-0">
                  <button @click="testWebhook(wh.id)"
                    :disabled="testingId === wh.id"
                    class="min-h-10 px-2 text-xs text-indigo-500 hover:text-indigo-600 font-medium transition-colors disabled:opacity-50">
                    {{ testingId === wh.id ? 'Sending...' : 'Test' }}
                  </button>
                  <button @click="toggleWebhook(wh)"
                    class="min-h-10 px-2 text-xs font-medium transition-colors"
                    :class="wh.is_active ? 'text-amber-500 hover:text-amber-600' : 'text-green-500 hover:text-green-600'">
                    {{ wh.is_active ? 'Pause' : 'Resume' }}
                  </button>
                  <button @click="deleteWebhook(wh.id)"
                    class="min-h-10 px-2 text-xs text-red-500 hover:text-red-600 font-medium transition-colors">
                    Delete
                  </button>
                </div>
              </div>
              <!-- Test result inline -->
              <div v-if="testingId === wh.id && testResult" class="mt-2">
                <span v-if="testResult.success" class="text-[11px] text-green-600 dark:text-green-400">
                  Delivered successfully ({{ testResult.status_code }})
                </span>
                <span v-else class="text-[11px] text-red-600 dark:text-red-400">
                  Failed: {{ testResult.error }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Webhook info sidebar -->
        <div class="space-y-4 min-w-0">
          <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
            <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Event Types</h2>
            <div class="space-y-2">
              <div v-for="evt in WEBHOOK_EVENT_TYPES" :key="evt.name" class="min-w-0">
                <code class="text-[11px] font-mono text-indigo-600 dark:text-indigo-400">{{ evt.name }}</code>
                <p class="text-[11px] text-gray-500 dark:text-gray-400">{{ evt.when }}</p>
              </div>
            </div>
            <p class="text-[11px] text-gray-400 dark:text-gray-500 mt-3">Delivery happens when a SimpleFIN sync finishes successfully and when a document import is confirmed.</p>
          </div>

          <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 min-w-0">
            <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Verifying Signatures</h2>
            <pre class="text-[11px] font-mono bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-lg p-3 overflow-x-auto text-gray-700 dark:text-gray-300">import hmac, hashlib

def verify(payload, secret, signature):
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)</pre>
            <p class="text-[11px] text-gray-400 dark:text-gray-500 mt-2">
              The signature is sent in the <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded">X-Webhook-Signature</code> header.
              Event type is in <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded">X-Webhook-Event</code>.
            </p>
          </div>

          <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
            <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">Retry Policy</h2>
            <p class="text-xs text-gray-500 dark:text-gray-400">
              Webhooks are deactivated after 10 consecutive delivery failures.
              Resume a paused webhook to reset the failure counter.
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ API Reference Tab ═══ -->
    <div v-show="activeTab === 'docs'">
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-8 text-center">
        <div class="max-w-md mx-auto">
          <svg class="w-12 h-12 mx-auto text-indigo-500 mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
          </svg>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-2">Interactive API Reference</h2>
          <p class="text-sm text-gray-500 dark:text-gray-400 mb-6">
            Browse all endpoints, view request and response schemas, and try calls in the Scalar viewer.
          </p>
          <a :href="scalarUrl" target="_blank" rel="noopener"
            class="inline-flex items-center gap-2 min-h-10 px-5 py-2.5 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
            Open API Reference
          </a>
          <p class="text-[11px] text-gray-400 dark:text-gray-500 mt-4 break-all">
            Powered by Scalar &middot; OpenAPI 3.1 &middot; {{ API }}/api/v1/openapi.json
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
