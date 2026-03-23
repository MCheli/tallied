<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ── Tabs ─────────────────────────────────────────────────────────────────────
const activeTab = ref<'keys' | 'webhooks' | 'docs'>('keys')

// ── API Keys ─────────────────────────────────────────────────────────────────
interface ApiKey {
  id: number
  name: string
  key_prefix: string
  permissions: string
  is_active: boolean
  last_used: string | null
  created_at: string | null
}

const keys = ref<ApiKey[]>([])
const loading = ref(true)

const showCreate = ref(false)
const newName = ref('')
const newPermissions = ref('read')
const creating = ref(false)

const createdKey = ref<string | null>(null)
const copied = ref(false)

async function loadKeys() {
  loading.value = true
  try {
    const res = await fetch(`${API}/api/v1/api-keys/`, { credentials: 'include' })
    keys.value = await res.json()
  } catch { /* */ }
  loading.value = false
}

async function createKey() {
  if (!newName.value.trim()) return
  creating.value = true
  try {
    const res = await fetch(`${API}/api/v1/api-keys/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ name: newName.value.trim(), permissions: newPermissions.value }),
    })
    const data = await res.json()
    createdKey.value = data.key
    newName.value = ''
    showCreate.value = false
    await loadKeys()
  } catch { /* */ }
  creating.value = false
}

async function revokeKey(id: number) {
  await fetch(`${API}/api/v1/api-keys/${id}`, { method: 'DELETE', credentials: 'include' })
  await loadKeys()
}

function copyKey() {
  if (createdKey.value) {
    navigator.clipboard.writeText(createdKey.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  }
}

function dismissCreatedKey() {
  createdKey.value = null
  copied.value = false
}

function fmtDate(iso: string | null): string {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtNum(n: number): string {
  return n.toLocaleString()
}

// ── Usage stats ──────────────────────────────────────────────────────────────
interface EndpointUsage {
  path: string
  method: string
  count: number
}

interface KeyUsageInfo {
  key_id: number
  key_name: string
  total_requests: number
  requests_last_24h: number
  requests_last_hour: number
  avg_latency_ms: number
  top_endpoints: EndpointUsage[]
}

interface UsageSummary {
  total_requests_today: number
  requests_last_hour: number
  total_requests_all_time: number
  avg_latency_ms: number
  top_endpoints: EndpointUsage[]
  per_key: KeyUsageInfo[]
}

const usage = ref<UsageSummary | null>(null)
const usageLoading = ref(false)

const keyUsage24h = computed(() => {
  const map = new Map<number, number>()
  if (usage.value) {
    for (const k of usage.value.per_key) {
      map.set(k.key_id, k.requests_last_24h)
    }
  }
  return map
})

async function loadUsage() {
  usageLoading.value = true
  try {
    const res = await fetch(`${API}/api/v1/api-keys/usage/summary`, { credentials: 'include' })
    if (res.ok) {
      usage.value = await res.json()
    }
  } catch { /* */ }
  usageLoading.value = false
}

// ── Webhooks ─────────────────────────────────────────────────────────────────
interface Webhook {
  id: number
  url: string
  events: string[]
  is_active: boolean
  created_at: string | null
  last_delivery: string | null
  failure_count: number
}

const WEBHOOK_EVENT_TYPES = [
  'transaction.created',
  'balance.updated',
  'import.completed',
  'account.created',
]

const webhooks = ref<Webhook[]>([])
const webhooksLoading = ref(true)

const showCreateWebhook = ref(false)
const newWebhookUrl = ref('')
const newWebhookEvents = ref<string[]>([])
const creatingWebhook = ref(false)

const createdSecret = ref<string | null>(null)
const secretCopied = ref(false)

const testingId = ref<number | null>(null)
const testResult = ref<{ success: boolean; status_code?: number; error?: string } | null>(null)

async function loadWebhooks() {
  webhooksLoading.value = true
  try {
    const res = await fetch(`${API}/api/v1/webhooks/`, { credentials: 'include' })
    webhooks.value = await res.json()
  } catch { /* */ }
  webhooksLoading.value = false
}

async function createWebhook() {
  if (!newWebhookUrl.value.trim() || newWebhookEvents.value.length === 0) return
  creatingWebhook.value = true
  try {
    const res = await fetch(`${API}/api/v1/webhooks/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ url: newWebhookUrl.value.trim(), events: newWebhookEvents.value }),
    })
    const data = await res.json()
    createdSecret.value = data.secret
    newWebhookUrl.value = ''
    newWebhookEvents.value = []
    showCreateWebhook.value = false
    await loadWebhooks()
  } catch { /* */ }
  creatingWebhook.value = false
}

async function deleteWebhook(id: number) {
  await fetch(`${API}/api/v1/webhooks/${id}`, { method: 'DELETE', credentials: 'include' })
  await loadWebhooks()
}

async function toggleWebhook(wh: Webhook) {
  await fetch(`${API}/api/v1/webhooks/${wh.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ is_active: !wh.is_active }),
  })
  await loadWebhooks()
}

async function testWebhook(id: number) {
  testingId.value = id
  testResult.value = null
  try {
    const res = await fetch(`${API}/api/v1/webhooks/${id}/test`, {
      method: 'POST',
      credentials: 'include',
    })
    testResult.value = await res.json()
  } catch {
    testResult.value = { success: false, error: 'Request failed' }
  }
  setTimeout(() => {
    if (testingId.value === id) {
      testingId.value = null
      testResult.value = null
    }
  }, 4000)
}

function copySecret() {
  if (createdSecret.value) {
    navigator.clipboard.writeText(createdSecret.value)
    secretCopied.value = true
    setTimeout(() => (secretCopied.value = false), 2000)
  }
}

function dismissCreatedSecret() {
  createdSecret.value = null
  secretCopied.value = false
}

function toggleEvent(event: string) {
  const idx = newWebhookEvents.value.indexOf(event)
  if (idx >= 0) {
    newWebhookEvents.value.splice(idx, 1)
  } else {
    newWebhookEvents.value.push(event)
  }
}

// ── Scalar API Docs ──────────────────────────────────────────────────────────
const isDark = computed(() => document.documentElement.classList.contains('dark'))
const scalarUrl = computed(() => `${API}/api/v1/scalar?dark=${isDark.value ? '1' : '0'}`)

onMounted(() => {
  loadKeys()
  loadUsage()
  loadWebhooks()
})
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2">
        <h2 class="text-lg font-bold text-gray-900 dark:text-white">API</h2>
        <InfoTooltip text="<strong>API Access</strong><br>Create API keys for programmatic access to your financial data. Authenticate with <code>X-API-Key</code> header." />
      </div>
    </div>

    <!-- Tab bar -->
    <div class="flex gap-1 mb-5">
      <button
        @click="activeTab = 'keys'"
        :class="[
          'px-4 py-2 rounded-lg text-xs font-medium transition-colors',
          activeTab === 'keys'
            ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300'
            : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
        ]"
      >Keys & Usage</button>
      <button
        @click="activeTab = 'webhooks'"
        :class="[
          'px-4 py-2 rounded-lg text-xs font-medium transition-colors',
          activeTab === 'webhooks'
            ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300'
            : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
        ]"
      >Webhooks</button>
      <button
        @click="activeTab = 'docs'"
        :class="[
          'px-4 py-2 rounded-lg text-xs font-medium transition-colors',
          activeTab === 'docs'
            ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300'
            : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
        ]"
      >API Reference</button>
    </div>

    <!-- ═══ Keys & Usage Tab ═══ -->
    <div v-show="activeTab === 'keys'">
      <!-- Newly created key banner -->
      <div v-if="createdKey" class="mb-6 bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 rounded-xl p-5">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-sm font-semibold text-green-800 dark:text-green-300">API Key Created</h3>
          <button @click="dismissCreatedKey" class="text-green-400 hover:text-green-600 text-xs">Dismiss</button>
        </div>
        <p class="text-xs text-green-700 dark:text-green-400 mb-3">Copy this key now — it won't be shown again.</p>
        <div class="flex items-center gap-2">
          <code class="flex-1 px-3 py-2 text-xs font-mono bg-white dark:bg-gray-900 border border-green-200 dark:border-green-700 rounded-lg text-gray-800 dark:text-gray-200 select-all break-all">{{ createdKey }}</code>
          <button @click="copyKey"
            class="px-3 py-2 text-xs font-medium rounded-lg transition-colors"
            :class="copied ? 'bg-green-600 text-white' : 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 hover:bg-green-200 dark:hover:bg-green-800'"
          >{{ copied ? 'Copied!' : 'Copy' }}</button>
        </div>
      </div>

      <!-- Usage Stats Banner -->
      <div v-if="usage" class="mb-6 grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3">
          <p class="text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500">Today</p>
          <p class="text-lg font-bold text-gray-900 dark:text-white">{{ fmtNum(usage.total_requests_today) }}</p>
          <p class="text-[10px] text-gray-400">requests</p>
        </div>
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3">
          <p class="text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500">Last Hour</p>
          <p class="text-lg font-bold text-gray-900 dark:text-white">{{ fmtNum(usage.requests_last_hour) }}</p>
          <p class="text-[10px] text-gray-400">requests</p>
        </div>
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3">
          <p class="text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500">All Time</p>
          <p class="text-lg font-bold text-gray-900 dark:text-white">{{ fmtNum(usage.total_requests_all_time) }}</p>
          <p class="text-[10px] text-gray-400">requests</p>
        </div>
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3">
          <p class="text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500">Avg Latency</p>
          <p class="text-lg font-bold text-gray-900 dark:text-white">{{ usage.avg_latency_ms }}<span class="text-xs font-normal text-gray-400">ms</span></p>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- API Keys Card -->
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
          <div class="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-gray-800">
            <div>
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">API Keys</h3>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Manage programmatic access to your data</p>
            </div>
            <button
              @click="showCreate = !showCreate"
              class="px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
            >{{ showCreate ? 'Cancel' : 'New Key' }}</button>
          </div>

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
                  <option value="read">Read only</option>
                  <option value="write">Read + Write</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <button @click="createKey" :disabled="creating || !newName.trim()"
                class="w-full px-3 py-2 text-xs font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors">
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
            <div v-for="key in keys" :key="key.id" class="px-5 py-3 flex items-center justify-between">
              <div>
                <div class="flex items-center gap-2">
                  <span class="text-xs font-medium text-gray-900 dark:text-white">{{ key.name }}</span>
                  <span :class="[
                    'text-[10px] px-1.5 py-0.5 rounded-full font-medium',
                    key.is_active
                      ? 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-400'
                      : 'bg-gray-100 dark:bg-gray-800 text-gray-400'
                  ]">{{ key.is_active ? key.permissions : 'revoked' }}</span>
                  <span v-if="keyUsage24h.has(key.id)"
                    class="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
                    {{ fmtNum(keyUsage24h.get(key.id) ?? 0) }} req/24h
                  </span>
                </div>
                <div class="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5 font-mono">
                  {{ key.key_prefix }}...
                  <span class="ml-2 font-sans">Created {{ fmtDate(key.created_at) }}</span>
                  <span v-if="key.last_used" class="ml-2 font-sans">Last used {{ fmtDate(key.last_used) }}</span>
                </div>
              </div>
              <button v-if="key.is_active" @click="revokeKey(key.id)"
                class="text-xs text-red-500 hover:text-red-600 font-medium transition-colors">
                Revoke
              </button>
            </div>
          </div>
        </div>

        <!-- Right column: Top Endpoints + Quick Start -->
        <div class="space-y-4">
          <!-- Top Endpoints -->
          <div v-if="usage && usage.top_endpoints.length > 0" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
            <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-800">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Most-Used Endpoints</h3>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">All time</p>
            </div>
            <table class="w-full text-xs">
              <thead>
                <tr class="border-b border-gray-100 dark:border-gray-800">
                  <th class="text-left px-5 py-2 text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">Method</th>
                  <th class="text-left px-5 py-2 text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">Path</th>
                  <th class="text-right px-5 py-2 text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">Requests</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-50 dark:divide-gray-800">
                <tr v-for="ep in usage.top_endpoints" :key="ep.method + ep.path">
                  <td class="px-5 py-2">
                    <span :class="[
                      'text-[10px] font-mono font-bold px-1.5 py-0.5 rounded',
                      ep.method === 'GET' ? 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400' :
                      ep.method === 'POST' ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400' :
                      ep.method === 'DELETE' ? 'bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400' :
                      'bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
                    ]">{{ ep.method }}</span>
                  </td>
                  <td class="px-5 py-2 font-mono text-gray-700 dark:text-gray-300">{{ ep.path }}</td>
                  <td class="px-5 py-2 text-right text-gray-900 dark:text-white font-medium">{{ fmtNum(ep.count) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Quick Start -->
          <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Quick Start</h3>
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
          <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">Base URL</h3>
            <code class="text-xs font-mono px-3 py-2 bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-lg block text-gray-700 dark:text-gray-300">{{ API }}/api/v1</code>
            <p class="text-[10px] text-gray-400 dark:text-gray-500 mt-2">All endpoints require authentication via <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded">X-API-Key</code> header or session cookie.</p>
          </div>

          <!-- Rate Limits -->
          <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">Rate Limits</h3>
            <p class="text-xs text-gray-600 dark:text-gray-400">Each API key is limited to <strong class="text-gray-900 dark:text-white">1,000 requests per hour</strong> (sliding window). Every response includes headers to help you track your usage:</p>
            <div class="mt-3 space-y-1">
              <div class="flex items-center gap-2 text-[11px] font-mono text-gray-600 dark:text-gray-400">
                <code class="bg-gray-50 dark:bg-gray-950 px-2 py-0.5 rounded border border-gray-200 dark:border-gray-800">X-RateLimit-Limit</code>
                <span class="text-gray-400 dark:text-gray-500">max requests per hour</span>
              </div>
              <div class="flex items-center gap-2 text-[11px] font-mono text-gray-600 dark:text-gray-400">
                <code class="bg-gray-50 dark:bg-gray-950 px-2 py-0.5 rounded border border-gray-200 dark:border-gray-800">X-RateLimit-Remaining</code>
                <span class="text-gray-400 dark:text-gray-500">requests remaining</span>
              </div>
              <div class="flex items-center gap-2 text-[11px] font-mono text-gray-600 dark:text-gray-400">
                <code class="bg-gray-50 dark:bg-gray-950 px-2 py-0.5 rounded border border-gray-200 dark:border-gray-800">X-RateLimit-Reset</code>
                <span class="text-gray-400 dark:text-gray-500">window reset (unix timestamp)</span>
              </div>
            </div>
            <p class="text-[10px] text-gray-400 dark:text-gray-500 mt-3">When the limit is exceeded, the API returns <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded">429 Too Many Requests</code> with a <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded">Retry-After</code> header.</p>
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
          <button @click="dismissCreatedSecret" class="text-green-400 hover:text-green-600 text-xs">Dismiss</button>
        </div>
        <p class="text-xs text-green-700 dark:text-green-400 mb-3">Copy the signing secret now — it won't be shown again. Use it to verify webhook signatures.</p>
        <div class="flex items-center gap-2">
          <code class="flex-1 px-3 py-2 text-xs font-mono bg-white dark:bg-gray-900 border border-green-200 dark:border-green-700 rounded-lg text-gray-800 dark:text-gray-200 select-all break-all">{{ createdSecret }}</code>
          <button @click="copySecret"
            class="px-3 py-2 text-xs font-medium rounded-lg transition-colors"
            :class="secretCopied ? 'bg-green-600 text-white' : 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 hover:bg-green-200 dark:hover:bg-green-800'"
          >{{ secretCopied ? 'Copied!' : 'Copy' }}</button>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Webhooks list -->
        <div class="lg:col-span-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
          <div class="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-gray-800">
            <div>
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Webhook Subscriptions</h3>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Receive HTTP notifications when events occur</p>
            </div>
            <button
              @click="showCreateWebhook = !showCreateWebhook"
              class="px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
            >{{ showCreateWebhook ? 'Cancel' : 'New Webhook' }}</button>
          </div>

          <!-- Create form -->
          <div v-if="showCreateWebhook" class="px-5 py-4 border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/30">
            <div class="space-y-3">
              <div>
                <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Payload URL</label>
                <input v-model="newWebhookUrl" type="url" placeholder="https://example.com/webhook"
                  class="w-full px-3 py-2 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
              </div>
              <div>
                <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Events</label>
                <div class="grid grid-cols-2 gap-2">
                  <label v-for="evt in WEBHOOK_EVENT_TYPES" :key="evt"
                    class="flex items-center gap-2 px-3 py-2 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors"
                    :class="newWebhookEvents.includes(evt) ? 'border-indigo-400 dark:border-indigo-600 bg-indigo-50 dark:bg-indigo-950/30' : ''">
                    <input type="checkbox" :checked="newWebhookEvents.includes(evt)" @change="toggleEvent(evt)"
                      class="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500" />
                    <span class="font-mono text-gray-700 dark:text-gray-300">{{ evt }}</span>
                  </label>
                </div>
              </div>
              <button @click="createWebhook" :disabled="creatingWebhook || !newWebhookUrl.trim() || newWebhookEvents.length === 0"
                class="w-full px-3 py-2 text-xs font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors">
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
            <div v-for="wh in webhooks" :key="wh.id" class="px-5 py-4">
              <div class="flex items-start justify-between">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-1">
                    <span class="text-xs font-mono text-gray-900 dark:text-white truncate">{{ wh.url }}</span>
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
                  <div class="text-[10px] text-gray-400 dark:text-gray-500">
                    Created {{ fmtDate(wh.created_at) }}
                    <span class="ml-2">Last delivery: {{ fmtDate(wh.last_delivery) }}</span>
                  </div>
                </div>
                <div class="flex items-center gap-2 ml-3 shrink-0">
                  <button @click="testWebhook(wh.id)"
                    :disabled="testingId === wh.id"
                    class="text-xs text-indigo-500 hover:text-indigo-600 font-medium transition-colors disabled:opacity-50">
                    {{ testingId === wh.id ? 'Sending...' : 'Test' }}
                  </button>
                  <button @click="toggleWebhook(wh)"
                    class="text-xs font-medium transition-colors"
                    :class="wh.is_active ? 'text-amber-500 hover:text-amber-600' : 'text-green-500 hover:text-green-600'">
                    {{ wh.is_active ? 'Pause' : 'Resume' }}
                  </button>
                  <button @click="deleteWebhook(wh.id)"
                    class="text-xs text-red-500 hover:text-red-600 font-medium transition-colors">
                    Delete
                  </button>
                </div>
              </div>
              <!-- Test result inline -->
              <div v-if="testingId === wh.id && testResult" class="mt-2">
                <span v-if="testResult.success" class="text-[10px] text-green-600 dark:text-green-400">
                  Delivered successfully ({{ testResult.status_code }})
                </span>
                <span v-else class="text-[10px] text-red-600 dark:text-red-400">
                  Failed: {{ testResult.error }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Webhook info sidebar -->
        <div class="space-y-4">
          <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Event Types</h3>
            <div class="space-y-2">
              <div v-for="evt in WEBHOOK_EVENT_TYPES" :key="evt">
                <code class="text-[11px] font-mono text-indigo-600 dark:text-indigo-400">{{ evt }}</code>
              </div>
            </div>
          </div>

          <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Verifying Signatures</h3>
            <pre class="text-[11px] font-mono bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-lg p-3 overflow-x-auto text-gray-700 dark:text-gray-300">import hmac, hashlib

def verify(payload, secret, signature):
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)</pre>
            <p class="text-[10px] text-gray-400 dark:text-gray-500 mt-2">
              The signature is sent in the <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded">X-Webhook-Signature</code> header.
              Event type is in <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded">X-Webhook-Event</code>.
            </p>
          </div>

          <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">Retry Policy</h3>
            <p class="text-xs text-gray-500 dark:text-gray-400">
              Webhooks are deactivated after 10 consecutive delivery failures.
              Re-enable a paused webhook to reset the failure counter.
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
          <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-2">Interactive API Reference</h3>
          <p class="text-sm text-gray-500 dark:text-gray-400 mb-6">
            Browse all endpoints, view request/response schemas, and test API calls with the interactive Scalar documentation viewer.
          </p>
          <a :href="scalarUrl" target="_blank"
            class="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
            Open API Reference
          </a>
          <p class="text-[10px] text-gray-400 dark:text-gray-500 mt-4">
            Powered by Scalar &middot; OpenAPI 3.1 &middot; {{ API }}/api/v1/openapi.json
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
