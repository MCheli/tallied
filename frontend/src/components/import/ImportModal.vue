<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useImportModal } from '../../composables/useImportModal'
import { X, Upload, Check, AlertTriangle, Send, Loader2 } from 'lucide-vue-next'
import { marked } from 'marked'

// Configure marked for safe inline rendering
marked.setOptions({ breaks: true, gfm: true })

function renderMd(text: string): string {
  return marked.parse(text) as string
}

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const { isOpen, context, closeImport } = useImportModal()

type Step = 'upload' | 'processing' | 'review' | 'done'
const step = ref<Step>('upload')

// Upload state
const fileQueue = ref<File[]>([])
const currentFileIdx = ref(0)

// Session state
const sessionId = ref('')
const aiSummary = ref('')
const missingFields = ref<any[]>([])
const proposedChanges = ref<any[]>([])
const acceptedIds = ref<Set<string>>(new Set())
const showDetail = ref(true)
type ReviewView = 'review' | 'sql'
const reviewView = ref<ReviewView>('review')
const changesApplied = ref(0)

// Chat state
const chatMessages = ref<any[]>([])
const chatInput = ref('')
const chatSending = ref(false)
const chatRef = ref<HTMLElement | null>(null)
const pendingAction = ref<any>(null)

// Config
const importConfig = ref<any>(null)

// Guidance text by context
const CONTEXT_LABELS: Record<string, string> = {
  income: 'Income', retirement: '401(k) / Retirement', property: 'Property / Mortgage',
  rsu: 'RSU Holdings', general: 'Financial Document',
}

watch(isOpen, async (open) => {
  if (open) {
    step.value = 'upload'
    fileQueue.value = []
    currentFileIdx.value = 0
    sessionId.value = ''
    aiSummary.value = ''
    missingFields.value = []
    proposedChanges.value = []
    acceptedIds.value = new Set()
    chatMessages.value = []
    changesApplied.value = 0
    pendingAction.value = null
    // Fetch config for context
    try {
      const res = await fetch(`${API}/api/v1/import/config/${context.value}`)
      if (res.ok) importConfig.value = await res.json()
    } catch {}
  }
})

function onFileDrop(e: DragEvent) {
  e.preventDefault()
  if (e.dataTransfer?.files) addFiles(e.dataTransfer.files)
}

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) addFiles(input.files)
  input.value = ''
}

function addFiles(files: FileList) {
  for (const f of files) fileQueue.value.push(f)
}

async function startProcessing() {
  if (fileQueue.value.length === 0) return
  currentFileIdx.value = 0
  await processFile(0)
}

async function processFile(idx: number) {
  const file = fileQueue.value[idx]
  if (!file) return
  step.value = 'processing'

  const formData = new FormData()
  formData.append('file', file)
  formData.append('context', context.value)

  try {
    const res = await fetch(`${API}/api/v1/import/upload`, { method: 'POST', body: formData })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(text)
    }
    const data = await res.json()
    sessionId.value = data.session_id
    aiSummary.value = data.ai_summary || ''
    missingFields.value = data.missing_fields || []
    proposedChanges.value = data.proposed_changes || []
    // Default: accept all
    acceptedIds.value = new Set(proposedChanges.value.map((c: any) => c.id))

    // Seed the chat with an AI summary message
    if (data.ai_summary) {
      // Ask the AI to explain what it found
      chatSending.value = true
      try {
        const chatRes = await fetch(`${API}/api/v1/import/${data.session_id}/chat`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: `Briefly summarize what you found in this document that's relevant to our app. Focus only on the specific database fields we track — mention the actual values found and whether they're new or updating existing data. If no changes are needed (data already matches), say so clearly. Keep it concise.` }),
        })
        const chatData = await chatRes.json()
        chatMessages.value = chatData.messages || []
      } catch {}
      chatSending.value = false
    }

    step.value = 'review'
  } catch (e: any) {
    aiSummary.value = `Error: ${e.message}`
    step.value = 'review'
  }
}

function toggleChange(id: string) {
  const s = new Set(acceptedIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  acceptedIds.value = s
}

async function confirmChanges() {
  if (!sessionId.value) return
  // Send accepted IDs
  await fetch(`${API}/api/v1/import/${sessionId.value}/accept`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ accepted_change_ids: [...acceptedIds.value] }),
  })
  // Confirm
  const res = await fetch(`${API}/api/v1/import/${sessionId.value}/confirm`, { method: 'POST' })
  const data = await res.json()
  changesApplied.value = data.changes_applied || 0

  // Check if more files in queue
  if (currentFileIdx.value < fileQueue.value.length - 1) {
    currentFileIdx.value++
    chatMessages.value = []
    pendingAction.value = null
    await processFile(currentFileIdx.value)
  } else {
    step.value = 'done'
  }
}

function skipFile() {
  if (currentFileIdx.value < fileQueue.value.length - 1) {
    currentFileIdx.value++
    chatMessages.value = []
    pendingAction.value = null
    processFile(currentFileIdx.value)
  } else {
    step.value = 'done'
  }
}

async function sendChat() {
  if (!chatInput.value.trim() || !sessionId.value) return
  const msg = chatInput.value.trim()
  chatInput.value = ''
  chatMessages.value.push({ role: 'user', content: msg })
  chatSending.value = true

  try {
    const res = await fetch(`${API}/api/v1/import/${sessionId.value}/chat`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    })
    const data = await res.json()
    chatMessages.value.push({ role: 'assistant', content: data.response, action: data.action })
    if (data.action) pendingAction.value = data.action
  } catch (e: any) {
    chatMessages.value.push({ role: 'assistant', content: `Error: ${e.message}` })
  }
  chatSending.value = false
  await nextTick()
  chatRef.value?.scrollTo({ top: chatRef.value.scrollHeight })
}

async function acceptAction() {
  if (!pendingAction.value || !sessionId.value) return
  const res = await fetch(`${API}/api/v1/import/${sessionId.value}/apply-action`, { method: 'POST' })
  const data = await res.json()
  if (data.applied) {
    // Refresh proposed changes
    const sessRes = await fetch(`${API}/api/v1/import/${sessionId.value}`)
    const sessData = await sessRes.json()
    proposedChanges.value = sessData.proposed_changes || []
    acceptedIds.value = new Set(proposedChanges.value.map((c: any) => c.id))
    chatMessages.value.push({ role: 'system', content: `Applied: ${data.message}` })
  }
  pendingAction.value = null
}

// Generate SQL preview from proposed changes
const sqlPreview = computed(() => {
  const statements: { table: string; action: string; sql: string; recordLabel?: string | null; recordKey?: string | null; fields: any[] }[] = []

  for (const change of proposedChanges.value) {
    const table = change.table
    const fields = change.fields || []
    if (!fields.length) continue

    const setClauses = fields.map((f: any) => {
      const val = f._store_value ?? f.new_value
      const formatted = typeof val === 'string' ? `'${val}'` : val
      return `  ${f.column} = ${formatted}`
    })

    let sql = ''
    let action = ''
    const whereClause = change.record_key
      ? `WHERE ${change.record_key}`
      : table === 'w2_records' && change.tax_year
        ? `WHERE tax_year = ${change.tax_year}`
        : `WHERE id = (SELECT id FROM ${table} ORDER BY updated_at DESC LIMIT 1)`

    if (change.action === 'upsert' || change.action === 'update') {
      action = fields.some((f: any) => f.is_new && !f.old_value) ? 'INSERT/UPDATE' : 'UPDATE'
      sql = `-- Updating: ${change.record_label || table}\nUPDATE ${table}\nSET\n${setClauses.join(',\n')}\n${whereClause};`
    } else {
      action = 'INSERT'
      const cols = fields.map((f: any) => f.column).join(', ')
      const vals = fields.map((f: any) => {
        const v = f._store_value ?? f.new_value
        return typeof v === 'string' ? `'${v}'` : v
      }).join(', ')
      sql = `INSERT INTO ${table} (${cols})\nVALUES (${vals});`
    }

    statements.push({
      table,
      action,
      sql,
      recordLabel: change.record_label || null,
      recordKey: change.record_key || null,
      fields: fields.map((f: any) => ({
        column: f.column,
        old: f.old_value,
        new: f._store_value ?? f.new_value,
        is_new: f.is_new,
        format: f.format,
      })),
    })
  }

  return statements
})

function fmt(n: number | null | undefined, format?: string): string {
  if (n == null) return '--'
  if (format === 'percent') return `${n}%`
  return `$${Math.round(n).toLocaleString()}`
}

</script>

<template>
  <Teleport to="body">
    <div v-if="isOpen" class="fixed inset-0 z-50 flex items-center justify-center">
      <!-- Backdrop -->
      <div class="absolute inset-0 bg-black/50" @click="step === 'done' ? closeImport() : null"></div>

      <!-- Modal -->
      <div class="relative bg-white dark:bg-gray-900 rounded-2xl shadow-2xl flex flex-col"
        style="width: 90vw; height: 85vh; max-width: 1200px;">

        <!-- Header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <div>
            <h2 class="text-lg font-bold text-gray-900 dark:text-white">Import Data</h2>
            <p class="text-xs text-gray-500 mt-0.5">
              {{ CONTEXT_LABELS[context] || 'Financial Document' }}
              <span v-if="fileQueue.length > 1" class="text-gray-400 ml-2">
                File {{ currentFileIdx + 1 }} of {{ fileQueue.length }}
              </span>
            </p>
          </div>
          <button @click="closeImport()" class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400">
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 overflow-hidden flex">

          <!-- ═══ UPLOAD STEP ═══ -->
          <div v-if="step === 'upload'" class="flex-1 flex flex-col items-center justify-center p-8">
            <div class="w-full max-w-lg">
              <!-- Drop zone -->
              <div class="border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-xl p-12 text-center cursor-pointer hover:border-indigo-400 transition-colors"
                @dragover.prevent @drop="onFileDrop" @click="($refs.fileInput as HTMLInputElement)?.click()">
                <Upload class="w-10 h-10 text-gray-400 mx-auto mb-3" />
                <p class="text-sm text-gray-600 dark:text-gray-400">Drop files here or click to browse</p>
                <p class="text-xs text-gray-400 mt-1">PDF, XLSX, CSV supported</p>
                <input ref="fileInput" type="file" accept=".pdf,.xlsx,.xls,.csv" multiple class="hidden" @change="onFileSelect" />
              </div>

              <!-- Queued files -->
              <div v-if="fileQueue.length > 0" class="mt-4 space-y-2">
                <div v-for="(f, i) in fileQueue" :key="i" class="flex items-center gap-3 px-3 py-2 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm">
                  <span class="text-gray-600 dark:text-gray-400 flex-1 truncate">{{ f.name }}</span>
                  <span class="text-xs text-gray-400">{{ (f.size / 1024).toFixed(0) }}KB</span>
                  <button @click="fileQueue.splice(i, 1)" class="text-gray-400 hover:text-red-500 text-xs">Remove</button>
                </div>
              </div>

              <!-- Guidance -->
              <div v-if="importConfig" class="mt-6 bg-indigo-50 dark:bg-indigo-950/30 rounded-lg p-4">
                <p class="text-xs text-indigo-700 dark:text-indigo-300 font-medium mb-1">{{ importConfig.guidance }}</p>
                <ul class="text-xs text-indigo-600 dark:text-indigo-400 space-y-0.5">
                  <li v-for="ex in importConfig.examples" :key="ex">• {{ ex }}</li>
                </ul>
              </div>

              <button v-if="fileQueue.length > 0" @click="startProcessing"
                class="mt-6 w-full py-3 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 transition-colors">
                Process {{ fileQueue.length }} file{{ fileQueue.length > 1 ? 's' : '' }}
              </button>
            </div>
          </div>

          <!-- ═══ PROCESSING STEP ═══ -->
          <div v-else-if="step === 'processing'" class="flex-1 flex flex-col items-center justify-center p-8">
            <Loader2 class="w-12 h-12 text-indigo-500 animate-spin mb-4" />
            <p class="text-sm text-gray-600 dark:text-gray-400">Analyzing {{ fileQueue[currentFileIdx]?.name }}...</p>
            <p class="text-xs text-gray-400 mt-2">AI is reading the document and extracting financial data</p>
          </div>

          <!-- ═══ REVIEW STEP ═══ -->
          <template v-else-if="step === 'review'">
            <!-- Left panel: changes -->
            <div class="flex-1 overflow-y-auto p-6 space-y-4">
              <!-- AI Summary -->
              <div class="bg-indigo-50 dark:bg-indigo-950/30 rounded-lg p-4">
                <p class="text-sm text-indigo-800 dark:text-indigo-200">{{ aiSummary }}</p>
              </div>

              <!-- Missing fields warning -->
              <div v-if="missingFields.length > 0" class="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg p-3">
                <div class="flex items-start gap-2">
                  <AlertTriangle class="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div class="text-xs text-amber-800 dark:text-amber-200">
                    <p class="font-medium mb-1">Expected data not found:</p>
                    <ul class="space-y-0.5">
                      <li v-for="m in missingFields" :key="m.field">
                        • {{ m.field.replace('w2_', '').replace('_', ' ') }} — try uploading a different document or use the chat to add manually
                      </li>
                    </ul>
                  </div>
                </div>
              </div>

              <!-- Proposed Changes -->
              <!-- View toggle -->
              <div v-if="proposedChanges.length > 0" class="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5 w-fit">
                <button @click="reviewView = 'review'"
                  class="px-4 py-1.5 text-xs font-medium rounded-md transition-colors"
                  :class="reviewView === 'review' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm' : 'text-gray-500'">
                  Review
                </button>
                <button @click="reviewView = 'sql'"
                  class="px-4 py-1.5 text-xs font-medium rounded-md transition-colors"
                  :class="reviewView === 'sql' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm' : 'text-gray-500'">
                  SQL Preview
                </button>
              </div>

              <!-- No changes state -->
              <div v-if="proposedChanges.length === 0" class="bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 rounded-lg p-4 text-center">
                <Check class="w-8 h-8 text-green-500 mx-auto mb-2" />
                <p class="text-sm font-medium text-green-800 dark:text-green-200">Everything is up to date</p>
                <p class="text-xs text-green-600 dark:text-green-400 mt-1">All values from this document already match what's in your database.</p>
              </div>

              <!-- ═══ SQL PREVIEW VIEW ═══ -->
              <div v-else-if="reviewView === 'sql'" class="space-y-4">
                <div v-for="stmt in sqlPreview" :key="stmt.table"
                  class="border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden">
                  <!-- Table header -->
                  <div class="px-4 py-2 bg-gray-50 dark:bg-gray-800/50 flex items-center justify-between">
                    <div class="flex items-center gap-2">
                      <span class="text-xs font-mono font-semibold text-gray-900 dark:text-white">{{ stmt.table }}</span>
                      <span class="text-[10px] px-1.5 py-0.5 rounded-full"
                        :class="stmt.action === 'INSERT' ? 'bg-green-100 dark:bg-green-900/30 text-green-700' : 'bg-amber-100 dark:bg-amber-900/30 text-amber-700'">
                        {{ stmt.action }}
                      </span>
                      <span v-if="stmt.recordLabel" class="text-xs font-semibold px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300">
                        {{ stmt.recordLabel }}
                      </span>
                    </div>
                    <span class="text-[10px] text-gray-400">{{ stmt.fields.length }} field{{ stmt.fields.length !== 1 ? 's' : '' }}</span>
                  </div>

                  <!-- Before/After table -->
                  <div class="px-4 py-2 border-b border-gray-100 dark:border-gray-800">
                    <table class="w-full text-xs">
                      <thead>
                        <tr class="text-gray-500">
                          <th class="text-left py-1 font-medium">Column</th>
                          <th class="text-right py-1 font-medium">Current</th>
                          <th class="text-center py-1 font-medium"></th>
                          <th class="text-right py-1 font-medium">New Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="f in stmt.fields" :key="f.column" class="border-t border-gray-50 dark:border-gray-800">
                          <td class="py-1 font-mono text-gray-700 dark:text-gray-300">{{ f.column }}</td>
                          <td class="py-1 text-right text-gray-400">{{ f.old != null ? (f.format === 'percent' ? f.old + '%' : f.old) : 'NULL' }}</td>
                          <td class="py-1 text-center text-gray-400">→</td>
                          <td class="py-1 text-right font-medium" :class="f.is_new ? 'text-green-600' : 'text-amber-600'">
                            {{ f.format === 'percent' ? f.new + '%' : f.new }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- SQL statement -->
                  <div class="px-4 py-3 bg-gray-900 dark:bg-black">
                    <pre class="text-xs font-mono text-green-400 whitespace-pre-wrap leading-relaxed">{{ stmt.sql }}</pre>
                  </div>
                </div>
              </div>

              <!-- ═══ REVIEW VIEW (accept/reject) ═══ -->
              <div v-else>
                <div class="flex items-center justify-between mb-2">
                  <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Database Changes</h3>
                  <button @click="showDetail = !showDetail" class="text-xs text-indigo-600 dark:text-indigo-400 hover:underline">
                    {{ showDetail ? 'Summary view' : 'Show details' }}
                  </button>
                </div>

                <div class="space-y-2">
                  <div v-for="change in proposedChanges" :key="change.id"
                    class="border rounded-lg overflow-hidden"
                    :class="acceptedIds.has(change.id) ? 'border-green-200 dark:border-green-800 bg-green-50/50 dark:bg-green-950/20' : 'border-gray-200 dark:border-gray-800 opacity-60'">
                    <!-- Change header -->
                    <div class="flex items-center gap-3 px-4 py-3 cursor-pointer" @click="toggleChange(change.id)">
                      <input type="checkbox" :checked="acceptedIds.has(change.id)" class="rounded" @click.stop="toggleChange(change.id)" />
                      <div class="flex-1">
                        <span class="text-sm font-medium text-gray-900 dark:text-white">{{ change.table.replace('_', ' ').replace(/\b\w/g, (l: string) => l.toUpperCase()) }}</span>
                        <span v-if="change.record_label" class="ml-2 text-xs font-semibold px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300">
                          {{ change.record_label }}
                        </span>
                        <span class="text-xs text-gray-400 ml-2">{{ change.fields.length }} field{{ change.fields.length !== 1 ? 's' : '' }}</span>
                      </div>
                      <span class="text-xs px-2 py-0.5 rounded-full"
                        :class="change.fields.some((f: any) => !f.is_new) ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700' : 'bg-green-100 dark:bg-green-900/30 text-green-700'">
                        {{ change.fields.some((f: any) => !f.is_new) ? 'Update' : 'New' }}
                      </span>
                    </div>

                    <!-- Detail view -->
                    <div v-if="showDetail" class="border-t border-gray-100 dark:border-gray-800 px-4 py-2 space-y-1">
                      <div v-for="f in change.fields" :key="f.column" class="flex items-center justify-between text-xs py-0.5">
                        <span class="text-gray-600 dark:text-gray-400">{{ f.display_name || f.column }}</span>
                        <div>
                          <span v-if="f.old_value != null && !f.is_new" class="text-gray-400 line-through mr-2">{{ fmt(f.old_value, f.format) }}</span>
                          <span class="font-medium" :class="f.is_new ? 'text-green-600' : 'text-amber-600'">
                            {{ typeof f.new_value === 'number' ? fmt(f.new_value, f.format) : f.new_value }}
                          </span>
                          <span v-if="f.source === 'user_corrected'" class="ml-1 text-indigo-500 text-[10px]">(manual)</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Right panel: Chat -->
            <div class="w-80 border-l border-gray-200 dark:border-gray-800 flex flex-col">
              <div class="px-4 py-3 border-b border-gray-100 dark:border-gray-800">
                <h3 class="text-xs font-semibold text-gray-900 dark:text-white">Ask AI</h3>
                <p class="text-[10px] text-gray-400 mt-0.5">Ask questions, request corrections</p>
              </div>

              <!-- Messages -->
              <div ref="chatRef" class="flex-1 overflow-y-auto p-4 space-y-3">
                <div v-if="chatMessages.length === 0" class="text-xs text-gray-400 text-center py-8">
                  Ask about the findings, or suggest corrections like "set base_salary to 155000"
                </div>
                <div v-for="(msg, i) in chatMessages" :key="i"
                  :class="msg.role === 'user' ? 'ml-6' : msg.role === 'system' ? 'text-center' : 'mr-6'">
                  <div v-if="msg.role === 'system'" class="text-[10px] text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-950/30 rounded px-2 py-1">
                    {{ msg.content }}
                  </div>
                  <div v-else class="rounded-lg px-3 py-2 text-xs"
                    :class="msg.role === 'user' ? 'bg-indigo-100 dark:bg-indigo-950 text-indigo-800 dark:text-indigo-200' : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 prose prose-xs dark:prose-invert max-w-none'">
                    <div v-if="msg.role === 'assistant'" v-html="renderMd(msg.content)"></div>
                    <span v-else>{{ msg.content }}</span>
                  </div>
                  <!-- Action button -->
                  <div v-if="msg.action && i === chatMessages.length - 1" class="mt-1.5">
                    <button @click="acceptAction"
                      class="text-[10px] bg-green-600 text-white px-3 py-1 rounded-lg hover:bg-green-700">
                      Accept: {{ msg.action.action === 'add_field' ? `Set ${msg.action.column} = ${msg.action.value}` : 'Apply change' }}
                    </button>
                  </div>
                </div>
                <div v-if="chatSending" class="mr-6">
                  <div class="bg-gray-100 dark:bg-gray-800 rounded-lg px-3 py-2 text-xs text-gray-400">
                    <Loader2 class="w-3 h-3 animate-spin inline mr-1" /> Thinking...
                  </div>
                </div>
              </div>

              <!-- Input -->
              <div class="p-3 border-t border-gray-100 dark:border-gray-800">
                <div class="flex gap-2">
                  <input v-model="chatInput" @keydown.enter="sendChat" :disabled="chatSending"
                    placeholder="Ask about findings..."
                    class="flex-1 px-3 py-2 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500" />
                  <button @click="sendChat" :disabled="chatSending || !chatInput.trim()"
                    class="p-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                    <Send class="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </template>

          <!-- ═══ DONE STEP ═══ -->
          <div v-else-if="step === 'done'" class="flex-1 flex flex-col items-center justify-center p-8">
            <div class="w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mb-4">
              <Check class="w-8 h-8 text-green-600" />
            </div>
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-2">Import Complete</h3>
            <p class="text-sm text-gray-500">
              {{ changesApplied }} change{{ changesApplied !== 1 ? 's' : '' }} applied to the database.
            </p>
            <p class="text-xs text-gray-400 mt-1">Data is now reflected across the app.</p>
            <button @click="closeImport()" class="mt-6 px-6 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700">
              Done
            </button>
          </div>

        </div>

        <!-- Footer (review step only) -->
        <div v-if="step === 'review'" class="px-6 py-4 border-t border-gray-200 dark:border-gray-800 flex items-center justify-between">
          <div class="text-xs text-gray-400">
            {{ acceptedIds.size }} of {{ proposedChanges.length }} change{{ proposedChanges.length !== 1 ? 's' : '' }} selected
            <span v-if="fileQueue.length > 1" class="ml-3">
              File {{ currentFileIdx + 1 }} of {{ fileQueue.length }}
            </span>
          </div>
          <div class="flex gap-3">
            <button v-if="proposedChanges.length > 0" @click="skipFile" class="px-4 py-2 text-sm text-gray-500 hover:text-gray-700">
              {{ currentFileIdx < fileQueue.length - 1 ? 'Skip File' : 'Cancel' }}
            </button>
            <button v-if="proposedChanges.length > 0" @click="confirmChanges" :disabled="acceptedIds.size === 0"
              class="px-6 py-2 text-sm font-medium bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50">
              Accept Selected Changes
            </button>
            <button v-if="proposedChanges.length === 0" @click="closeImport()"
              class="px-6 py-2 text-sm font-medium bg-gray-600 text-white rounded-lg hover:bg-gray-700">
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style>
.prose-xs {
  font-size: 12px;
  line-height: 1.6;
}
.prose-xs p { margin: 0.4em 0; }
.prose-xs h1, .prose-xs h2, .prose-xs h3 { font-size: 13px; font-weight: 600; margin: 0.6em 0 0.3em; }
.prose-xs ul, .prose-xs ol { padding-left: 1.2em; margin: 0.3em 0; }
.prose-xs li { margin: 0.15em 0; }
.prose-xs table { width: 100%; border-collapse: collapse; margin: 0.5em 0; font-size: 11px; }
.prose-xs th, .prose-xs td { border: 1px solid #e5e7eb; padding: 3px 6px; text-align: left; }
.prose-xs th { background: #f9fafb; font-weight: 600; }
.prose-xs strong { font-weight: 600; }
.prose-xs code { background: #f3f4f6; padding: 1px 4px; border-radius: 3px; font-size: 11px; }
.dark .prose-xs th, .dark .prose-xs td { border-color: #374151; }
.dark .prose-xs th { background: #1f2937; }
.dark .prose-xs code { background: #374151; }
</style>
