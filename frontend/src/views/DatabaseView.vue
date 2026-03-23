<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import { highlightSql } from '../composables/useSqlHighlight'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ColumnInfo {
  name: string
  type: string
  nullable: boolean
  primary_key: boolean
  default: string | null
  description?: string
}

interface ForeignKey {
  column: string
  references_table: string
  references_column: string
}

interface TableSchema {
  name: string
  description?: string
  columns: ColumnInfo[]
  foreign_keys: ForeignKey[]
  row_count: number
}

interface Edge {
  from_table: string
  from_column: string
  to_table: string
  to_column: string
}

interface SchemaResponse {
  tables: TableSchema[]
  edges: Edge[]
}

interface PreviewResponse {
  table: string
  columns: string[]
  rows: Record<string, unknown>[]
  total: number
  limit: number
  offset: number
}

interface QueryResponse {
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
  query: string
}

type TableCategory = 'financial' | 'investments' | 'property' | 'planning' | 'system'

interface DbCredentialResponse {
  id: number
  name: string
  pg_username: string
  access_level: string
  is_active: boolean
  created_at: string | null
}

interface DbCredentialCreatedResponse extends DbCredentialResponse {
  password: string
  host: string
  port: number
  database: string
  schema_name: string
  connection_string: string
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {}
  if (options?.method && options.method !== 'GET') {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers,
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

// ── State ─────────────────────────────────────────────────────────────────────

const schema = ref<SchemaResponse | null>(null)
const schemaLoading = ref(false)
const schemaError = ref<string | null>(null)

const selectedTable = ref<string | null>(null)
const centerMode = ref<'schema' | 'query' | 'access'>('schema')

// Data preview modal
const previewModalTable = ref<string | null>(null)
const showPreviewModal = computed(() => previewModalTable.value !== null)

// Canvas pan/zoom (Miro-style)
const isFullscreen = ref(false)
const erdContainer = ref<HTMLDivElement | null>(null)
const panX = ref(0)
const panY = ref(0)
const zoom = ref(1)
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0 })
const spaceHeld = ref(false)
const MIN_ZOOM = 0.15
const MAX_ZOOM = 3

function zoomIn() { zoomAt(zoom.value * 1.2, null) }
function zoomOut() { zoomAt(zoom.value / 1.2, null) }
function zoomReset() { zoom.value = 1; panX.value = 0; panY.value = 0 }
function zoomFit() {
  const el = erdContainer.value
  if (!el) return
  const cw = el.clientWidth
  const ch = el.clientHeight
  const sw = svgWidth.value
  const sh = svgHeight.value
  const fitZoom = Math.min(cw / sw, ch / sh, 1) * 0.9
  zoom.value = fitZoom
  panX.value = (cw - sw * fitZoom) / 2
  panY.value = (ch - sh * fitZoom) / 2
}
function toggleFullscreen() { isFullscreen.value = !isFullscreen.value; nextTick(zoomFit) }

function zoomAt(newZoom: number, center: { x: number; y: number } | null) {
  const clamped = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, newZoom))
  if (center) {
    // Zoom towards the cursor position
    const scale = clamped / zoom.value
    panX.value = center.x - (center.x - panX.value) * scale
    panY.value = center.y - (center.y - panY.value) * scale
  }
  zoom.value = clamped
}

// Wheel: zoom toward cursor (handles both scroll wheel and trackpad pinch)
function onWheel(e: WheelEvent) {
  e.preventDefault()
  const rect = erdContainer.value?.getBoundingClientRect()
  if (!rect) return
  const cx = e.clientX - rect.left
  const cy = e.clientY - rect.top

  if (e.ctrlKey) {
    // Pinch-to-zoom (trackpad sends ctrlKey + small deltaY)
    const factor = 1 - e.deltaY * 0.01
    zoomAt(zoom.value * factor, { x: cx, y: cy })
  } else {
    // Scroll wheel or two-finger pan on trackpad
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && !e.shiftKey && Math.abs(e.deltaY) > 10) {
      // Likely a discrete scroll wheel — zoom
      const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1
      zoomAt(zoom.value * factor, { x: cx, y: cy })
    } else {
      // Trackpad two-finger scroll — pan
      panX.value -= e.deltaX
      panY.value -= e.deltaY
    }
  }
}

// Mouse drag to pan (middle button, or left button on canvas background)
function onPointerDown(e: PointerEvent) {
  // Middle mouse button always pans
  if (e.button === 1 || spaceHeld.value) {
    e.preventDefault()
    isPanning.value = true
    panStart.value = { x: e.clientX - panX.value, y: e.clientY - panY.value }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
    return
  }
  // Left click on background (not on a card) also pans
  if (e.button === 0 && (e.target as SVGElement).tagName === 'svg') {
    isPanning.value = true
    panStart.value = { x: e.clientX - panX.value, y: e.clientY - panY.value }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }
}
function onPointerMove(e: PointerEvent) {
  if (!isPanning.value) return
  panX.value = e.clientX - panStart.value.x
  panY.value = e.clientY - panStart.value.y
}
function onPointerUp() {
  isPanning.value = false
}

// Space key for pan mode
function onKeyDown(e: KeyboardEvent) {
  if (e.code === 'Space' && !e.repeat && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
    e.preventDefault()
    spaceHeld.value = true
  }
}
function onKeyUp(e: KeyboardEvent) {
  if (e.code === 'Space') spaceHeld.value = false
}

const canvasTransform = computed(() =>
  `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`
)
const canvasCursor = computed(() =>
  isPanning.value ? 'grabbing' : spaceHeld.value ? 'grab' : 'default'
)

const searchQuery = ref('')
const sqlText = ref('')
const sqlRunning = ref(false)
const sqlError = ref<string | null>(null)
const sqlResult = ref<QueryResponse | null>(null)

const previewData = ref<PreviewResponse | null>(null)
const previewLoading = ref(false)
const previewError = ref<string | null>(null)
const previewOffset = ref(0)
const PAGE_SIZE = 20

const isDark = computed(() => typeof document !== 'undefined' && document.documentElement.classList.contains('dark'))

// ── Credential management state ──────────────────────────────────────────────

const credentials = ref<DbCredentialResponse[]>([])
const credLoading = ref(false)
const credCreating = ref(false)
const credRevoking = ref<number | null>(null)
const credError = ref<string | null>(null)
const credName = ref('')
const credAccessLevel = ref('read')
const newCredential = ref<DbCredentialCreatedResponse | null>(null)
const showCredentialModal = computed(() => newCredential.value !== null)
const copiedField = ref<string | null>(null)

// ── Category classification ───────────────────────────────────────────────────

const categoryMap: Record<string, TableCategory> = {}

const categoryPatterns: { category: TableCategory; patterns: string[] }[] = [
  { category: 'financial', patterns: ['accounts', 'transactions', 'balance_snapshots', 'w2_records'] },
  { category: 'investments', patterns: ['rsu_grants', 'vest_events', 'stock_prices', 'retirement'] },
  { category: 'property', patterns: ['mortgages', 'property_valuations', 'property'] },
  { category: 'planning', patterns: ['plan_', 'actual_snapshots', 'forecasts', 'contribution_configs'] },
  { category: 'system', patterns: ['users', 'import_logs', 'import_sessions', 'plaid_links', 'alembic'] },
]

function classifyTable(name: string): TableCategory {
  if (categoryMap[name]) return categoryMap[name]
  for (const { category, patterns } of categoryPatterns) {
    for (const p of patterns) {
      if (name === p || name.startsWith(p)) {
        categoryMap[name] = category
        return category
      }
    }
  }
  categoryMap[name] = 'system'
  return 'system'
}

const categoryColors: Record<TableCategory, { bg: string; border: string; text: string; badge: string; dot: string }> = {
  financial: {
    bg: 'bg-blue-50 dark:bg-blue-950/30',
    border: 'border-blue-200 dark:border-blue-800',
    text: 'text-blue-700 dark:text-blue-300',
    badge: 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300',
    dot: 'bg-blue-500',
  },
  investments: {
    bg: 'bg-emerald-50 dark:bg-emerald-950/30',
    border: 'border-emerald-200 dark:border-emerald-800',
    text: 'text-emerald-700 dark:text-emerald-300',
    badge: 'bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-300',
    dot: 'bg-emerald-500',
  },
  property: {
    bg: 'bg-amber-50 dark:bg-amber-950/30',
    border: 'border-amber-200 dark:border-amber-800',
    text: 'text-amber-700 dark:text-amber-300',
    badge: 'bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-300',
    dot: 'bg-amber-500',
  },
  planning: {
    bg: 'bg-purple-50 dark:bg-purple-950/30',
    border: 'border-purple-200 dark:border-purple-800',
    text: 'text-purple-700 dark:text-purple-300',
    badge: 'bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300',
    dot: 'bg-purple-500',
  },
  system: {
    bg: 'bg-gray-50 dark:bg-gray-800/30',
    border: 'border-gray-200 dark:border-gray-700',
    text: 'text-gray-600 dark:text-gray-400',
    badge: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
    dot: 'bg-gray-400',
  },
}

const categoryLabels: Record<TableCategory, string> = {
  financial: 'Financial',
  investments: 'Investments',
  property: 'Property',
  planning: 'Planning',
  system: 'System',
}

// ── Computed ──────────────────────────────────────────────────────────────────

const tables = computed(() => schema.value?.tables ?? [])
const edges = computed(() => schema.value?.edges ?? [])

const filteredTables = computed(() => {
  const q = searchQuery.value.toLowerCase().trim()
  const all = tables.value
  if (!q) return all
  return all.filter(t => t.name.toLowerCase().includes(q))
})

const groupedTables = computed(() => {
  const groups: Record<TableCategory, TableSchema[]> = {
    financial: [],
    investments: [],
    property: [],
    planning: [],
    system: [],
  }
  for (const t of filteredTables.value) {
    const cat = classifyTable(t.name)
    groups[cat].push(t)
  }
  // Sort each group alphabetically
  for (const cat of Object.keys(groups) as TableCategory[]) {
    groups[cat].sort((a, b) => a.name.localeCompare(b.name))
  }
  return groups
})

const previewTableSchema = computed(() =>
  tables.value.find(t => t.name === previewModalTable.value) ?? null
)

const previewFkColumns = computed(() => {
  if (!previewTableSchema.value) return new Map<string, { table: string; column: string }>()
  const map = new Map<string, { table: string; column: string }>()
  for (const fk of previewTableSchema.value.foreign_keys) {
    map.set(fk.column, { table: fk.references_table, column: fk.references_column })
  }
  for (const e of edges.value) {
    if (e.from_table === previewModalTable.value) {
      map.set(e.from_column, { table: e.to_table, column: e.to_column })
    }
  }
  return map
})

const relatedTables = computed(() => {
  if (!selectedTable.value) return new Set<string>()
  const related = new Set<string>()
  for (const e of edges.value) {
    if (e.from_table === selectedTable.value) related.add(e.to_table)
    if (e.to_table === selectedTable.value) related.add(e.from_table)
  }
  return related
})

const previewCurrentPage = computed(() =>
  previewData.value ? Math.floor(previewOffset.value / PAGE_SIZE) + 1 : 1
)

const previewTotalPages = computed(() =>
  previewData.value ? Math.ceil(previewData.value.total / PAGE_SIZE) : 0
)

// ── ERD Layout ────────────────────────────────────────────────────────────────

const CARD_W = 250
const CARD_GAP_X = 120
const CARD_GAP_Y = 60
const COLS = 4
const CARD_HEADER_H = 36
const CARD_ROW_H = 22
const CARD_PAD_Y = 8

function cardHeight(t: TableSchema): number {
  return CARD_HEADER_H + t.columns.length * CARD_ROW_H + CARD_PAD_Y * 2
}

interface CardLayout {
  table: TableSchema
  x: number
  y: number
  w: number
  h: number
}

const cardLayouts = computed((): CardLayout[] => {
  const layouts: CardLayout[] = []
  // Group by category for nicer layout
  const ordered: TableSchema[] = []
  for (const cat of ['financial', 'investments', 'property', 'planning', 'system'] as TableCategory[]) {
    const group = tables.value.filter(t => classifyTable(t.name) === cat)
    group.sort((a, b) => a.name.localeCompare(b.name))
    ordered.push(...group)
  }

  // Place cards in columns, tracking per-column Y
  const colYs = Array(COLS).fill(0)

  for (const t of ordered) {
    // Pick the shortest column
    let minCol = 0
    for (let c = 1; c < COLS; c++) {
      if (colYs[c] < colYs[minCol]) minCol = c
    }
    const x = minCol * (CARD_W + CARD_GAP_X) + 20
    const y = colYs[minCol] + 20
    const h = cardHeight(t)
    layouts.push({ table: t, x, y, w: CARD_W, h })
    colYs[minCol] = y + h + CARD_GAP_Y
  }
  return layouts
})

const svgWidth = computed(() => COLS * (CARD_W + CARD_GAP_X) + 40)
const svgHeight = computed(() => {
  let max = 0
  for (const c of cardLayouts.value) {
    if (c.y + c.h > max) max = c.y + c.h
  }
  return max + 40
})

interface EdgePath {
  edge: Edge
  path: string
}

// Orthogonal (H-V-H) edge routing — lines only go horizontal or vertical
const edgePaths = computed((): EdgePath[] => {
  const layoutMap = new Map<string, CardLayout>()
  for (const cl of cardLayouts.value) {
    layoutMap.set(cl.table.name, cl)
  }

  // Track how many edges exit from each side of each card to offset them
  const sideCounters = new Map<string, number>()
  function nextOffset(key: string): number {
    const n = sideCounters.get(key) ?? 0
    sideCounters.set(key, n + 1)
    return n * 6
  }

  return edges.value.map(e => {
    const from = layoutMap.get(e.from_table)
    const to = layoutMap.get(e.to_table)
    if (!from || !to) return null

    const fromColIdx = from.table.columns.findIndex(c => c.name === e.from_column)
    const toColIdx = to.table.columns.findIndex(c => c.name === e.to_column)

    const fromY = from.y + CARD_HEADER_H + CARD_PAD_Y + (fromColIdx >= 0 ? fromColIdx : 0) * CARD_ROW_H + CARD_ROW_H / 2
    const toY = to.y + CARD_HEADER_H + CARD_PAD_Y + (toColIdx >= 0 ? toColIdx : 0) * CARD_ROW_H + CARD_ROW_H / 2

    // Determine which side to exit/enter — pick sides that face each other
    const fromCenterX = from.x + from.w / 2
    const toCenterX = to.x + to.w / 2
    const GAP = 20 // min distance from card edge before first turn

    let fromX: number, toX: number, fromDir: number

    if (fromCenterX <= toCenterX) {
      // from is left of to — exit right, enter left
      fromX = from.x + from.w
      toX = to.x
      fromDir = 1
    } else {
      // from is right of to — exit left, enter right
      fromX = from.x
      toX = to.x + to.w
      fromDir = -1
    }

    const edgeKey = `${e.from_table}-${fromDir}`
    const offset = nextOffset(edgeKey)

    // Build orthogonal path: H out → V → H in
    const midX = (fromX + toX) / 2 + offset
    // If cards are in same column, route around
    if (Math.abs(fromX - toX) < CARD_W) {
      const routeX = fromDir === 1
        ? Math.max(from.x + from.w, to.x + to.w) + GAP + offset
        : Math.min(from.x, to.x) - GAP - offset
      const path = `M ${fromX} ${fromY} H ${routeX} V ${toY} H ${toX}`
      return { edge: e, path }
    }

    const path = `M ${fromX} ${fromY} H ${midX} V ${toY} H ${toX}`
    return { edge: e, path }
  }).filter(Boolean) as EdgePath[]
})

function isEdgeActive(ep: EdgePath): boolean {
  return !!selectedTable.value &&
    (ep.edge.from_table === selectedTable.value || ep.edge.to_table === selectedTable.value)
}

const activeEdgePaths = computed(() => edgePaths.value.filter(isEdgeActive))
const inactiveEdgePaths = computed(() =>
  selectedTable.value ? edgePaths.value.filter(ep => !isEdgeActive(ep)) : edgePaths.value
)

// ── Loaders ───────────────────────────────────────────────────────────────────

async function loadSchema() {
  schemaLoading.value = true
  schemaError.value = null
  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/schema`, { credentials: 'include' })
    if (!res.ok) throw new Error(`${res.status}`)
    schema.value = await res.json()
  } catch (e) {
    schemaError.value = e instanceof Error ? e.message : 'Failed to load schema'
  } finally {
    schemaLoading.value = false
  }
}

async function loadPreview(tableName: string, offset = 0) {
  previewLoading.value = true
  previewError.value = null
  try {
    previewData.value = await apiFetch<PreviewResponse>(
      `/api/v1/admin/tables/${encodeURIComponent(tableName)}/preview?limit=${PAGE_SIZE}&offset=${offset}`
    )
    previewOffset.value = offset
  } catch (e) {
    previewError.value = e instanceof Error ? e.message : 'Failed to load preview'
  } finally {
    previewLoading.value = false
  }
}

async function runSql() {
  if (!sqlText.value.trim()) return
  sqlRunning.value = true
  sqlError.value = null
  sqlResult.value = null
  try {
    sqlResult.value = await apiFetch<QueryResponse>('/api/v1/admin/query', {
      method: 'POST',
      body: JSON.stringify({ sql: sqlText.value.trim(), limit: 100 }),
    })
  } catch (e) {
    sqlError.value = e instanceof Error ? e.message : 'Query failed'
  } finally {
    sqlRunning.value = false
  }
}

// ── Interactions ──────────────────────────────────────────────────────────────

function selectTable(name: string) {
  selectedTable.value = name
  centerMode.value = 'schema'
  panToCard(name)
}

function selectTableFromErd(name: string) {
  selectedTable.value = name
  // Stay in schema mode, just highlight
}

function clickErdCard(name: string) {
  if (selectedTable.value === name) {
    // Double-click behavior: open preview modal
    openPreviewModal(name)
  } else {
    selectTableFromErd(name)
  }
}

function openPreviewModal(tableName: string) {
  previewModalTable.value = tableName
  loadPreview(tableName, 0)
}

function closePreviewModal() {
  previewModalTable.value = null
  previewData.value = null
  previewError.value = null
}

function jumpToFk(tableName: string, columnName: string, value: unknown) {
  if (value === null || value === undefined) return
  previewModalTable.value = tableName
  sqlText.value = `SELECT * FROM ${tableName} WHERE ${columnName} = '${value}' LIMIT 20`
  loadPreview(tableName, 0)
}

function prevPage() {
  if (!previewModalTable.value || previewOffset.value === 0) return
  loadPreview(previewModalTable.value, Math.max(0, previewOffset.value - PAGE_SIZE))
}

function nextPage() {
  if (!previewModalTable.value || !previewData.value) return
  if (previewOffset.value + PAGE_SIZE >= previewData.value.total) return
  loadPreview(previewModalTable.value, previewOffset.value + PAGE_SIZE)
}

const highlightedSqlText = computed(() => highlightSql(sqlText.value) + '\n')
// Used as template ref (ref="sqlEditorRef") — vue-tsc -b may not detect usage
// @ts-ignore TS6133
const sqlEditorRef = ref<HTMLTextAreaElement | null>(null)

function syncScroll(e: Event) {
  const ta = e.target as HTMLTextAreaElement
  const pre = ta.parentElement?.querySelector('.sql-highlight-layer') as HTMLElement | null
  if (pre) {
    pre.scrollTop = ta.scrollTop
    pre.scrollLeft = ta.scrollLeft
  }
}

function handleSqlKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault()
    runSql()
  }
}

// ── Credential management ────────────────────────────────────────────────────

async function loadCredentials() {
  credLoading.value = true
  try {
    credentials.value = await apiFetch<DbCredentialResponse[]>('/api/v1/db-credentials/')
  } catch {
    // Silently fail — credentials tab may not be active
  } finally {
    credLoading.value = false
  }
}

async function createCredential() {
  if (!credName.value.trim()) return
  credCreating.value = true
  credError.value = null
  try {
    const result = await apiFetch<DbCredentialCreatedResponse>('/api/v1/db-credentials/', {
      method: 'POST',
      body: JSON.stringify({ name: credName.value.trim(), access_level: credAccessLevel.value }),
    })
    newCredential.value = result
    credName.value = ''
    credAccessLevel.value = 'read'
    await loadCredentials()
  } catch (e) {
    credError.value = e instanceof Error ? e.message : 'Failed to create credential'
  } finally {
    credCreating.value = false
  }
}

async function revokeCredential(id: number) {
  credRevoking.value = id
  try {
    await apiFetch(`/api/v1/db-credentials/${id}`, { method: 'DELETE' })
    await loadCredentials()
  } catch {
    // Reload to get current state
    await loadCredentials()
  } finally {
    credRevoking.value = null
  }
}

function formatCredDate(dateStr: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

async function copyToClipboard(text: string, field?: string) {
  try {
    await navigator.clipboard.writeText(text)
    if (field) {
      copiedField.value = field
      setTimeout(() => { copiedField.value = null }, 2000)
    }
  } catch {
    // Silently fail
  }
}

function closeCredentialModal() {
  newCredential.value = null
  copiedField.value = null
}

function downloadCredentialsMd() {
  const c = newCredential.value
  if (!c) return
  const accessLabel = c.access_level === 'read' ? 'Read-only' : 'Read-write'
  const now = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
  const content = `# Tallied Database Credentials

**Created:** ${now}
**Name:** ${c.name}
**Access Level:** ${accessLabel}

## Connection Details
- **Host:** ${c.host}
- **Port:** ${c.port}
- **Database:** ${c.database}
- **Schema:** ${c.schema_name}
- **Username:** ${c.pg_username}
- **Password:** ${c.password}

## Connection String
\`\`\`
${c.connection_string}
\`\`\`

## Quick Start
### psql
\`\`\`bash
psql "${c.connection_string}"
\`\`\`

### Python
\`\`\`python
from sqlalchemy import create_engine
engine = create_engine("${c.connection_string}")
\`\`\`

> **Warning:** This file contains sensitive credentials. Store it securely.
`
  const blob = new Blob([content], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `tallied-credentials-${c.name.toLowerCase().replace(/\s+/g, '-')}.md`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatType(raw: string): string {
  const t = raw.toUpperCase()
  if (t.includes('VARCHAR') || t.includes('TEXT') || t.includes('CHAR')) return 'string'
  if (t.includes('INTEGER') || t.includes('INT') || t.includes('BIGINT') || t.includes('SMALLINT')) return 'int'
  if (t.includes('NUMERIC') || t.includes('DECIMAL') || t.includes('FLOAT') || t.includes('DOUBLE') || t.includes('REAL')) return 'decimal'
  if (t.includes('BOOLEAN') || t.includes('BOOL')) return 'bool'
  if (t.includes('TIMESTAMP') || t.includes('DATETIME')) return 'timestamp'
  if (t.includes('DATE')) return 'date'
  if (t.includes('JSON')) return 'json'
  if (t.includes('UUID')) return 'uuid'
  return raw.toLowerCase()
}

function formatCellValue(val: unknown): string {
  if (val === null || val === undefined) return '\u2014'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function isColumnPk(tableName: string, colName: string): boolean {
  const t = tables.value.find(tb => tb.name === tableName)
  if (!t) return false
  return t.columns.some(c => c.name === colName && c.primary_key)
}

function isColumnFk(tableName: string, colName: string): boolean {
  const t = tables.value.find(tb => tb.name === tableName)
  if (!t) return false
  if (t.foreign_keys.some(fk => fk.column === colName)) return true
  return edges.value.some(e => e.from_table === tableName && e.from_column === colName)
}

function panToCard(name: string) {
  const el = erdContainer.value
  if (!el) return
  const cl = cardLayouts.value.find(c => c.table.name === name)
  if (!cl) return
  // Center the card in the viewport
  const vw = el.clientWidth
  const vh = el.clientHeight
  const cardCenterX = cl.x + cl.w / 2
  const cardCenterY = cl.y + cl.h / 2
  panX.value = vw / 2 - cardCenterX * zoom.value
  panY.value = vh / 2 - cardCenterY * zoom.value
}

watch(selectedTable, () => {
  if (centerMode.value === 'schema' && selectedTable.value) {
    nextTick(() => panToCard(selectedTable.value!))
  }
})

// Load credentials when switching to access tab
watch(centerMode, (mode) => {
  if (mode === 'access' && credentials.value.length === 0) {
    loadCredentials()
  }
})

// ── Init ──────────────────────────────────────────────────────────────────────

onMounted(() => {
  loadSchema().then(() => nextTick(zoomFit))
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)

  // Check for pre-filled query from SQL transparency links
  const prefill = sessionStorage.getItem('sql-runner-query')
  if (prefill) {
    sessionStorage.removeItem('sql-runner-query')
    sqlText.value = prefill
    centerMode.value = 'query'
  }
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
})
</script>

<template>
  <div :class="[
    'flex flex-col min-h-0',
    isFullscreen ? 'fixed inset-0 z-50 bg-white dark:bg-gray-950 p-4' : 'h-[calc(100vh-120px)]'
  ]">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4 flex-shrink-0">
      <div class="flex items-center gap-2">
        <h2 class="text-lg font-bold text-gray-900 dark:text-white">Database</h2>
        <InfoTooltip text="<strong>Database Schema Canvas</strong><br>Browse your database tables, view their relationships, preview data, and run SQL queries." />
      </div>
      <div class="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
        <span v-if="schema">{{ tables.length }} tables</span>
        <span v-if="schema">&middot;</span>
        <span v-if="schema">{{ edges.length }} relationships</span>
        <button
          v-if="isFullscreen"
          @click="isFullscreen = false"
          class="ml-2 p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400"
          title="Exit fullscreen"
        >&times;</button>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="schemaLoading" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500 mx-auto mb-3"></div>
        <p class="text-sm text-gray-500 dark:text-gray-400">Loading database schema...</p>
      </div>
    </div>

    <!-- Error state -->
    <div v-else-if="schemaError" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <p class="text-sm text-red-500 mb-2">{{ schemaError }}</p>
        <button @click="loadSchema" class="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
          Retry
        </button>
      </div>
    </div>

    <!-- Main content -->
    <div v-else-if="schema" class="flex gap-4 flex-1 min-h-0">

      <!-- ═══ Left Panel: Table List ═══ -->
      <aside class="w-[250px] flex-shrink-0 flex flex-col bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
        <div class="px-3 py-2.5 border-b border-gray-100 dark:border-gray-800 flex items-center gap-1.5">
          <span class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Tables</span>
          <InfoTooltip text="<strong>Table List</strong><br>Click a table to preview its data. Tables are grouped by category: financial, investments, property, planning, and system." />
        </div>

        <!-- Search -->
        <div class="px-3 py-2 border-b border-gray-100 dark:border-gray-800">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Filter tables..."
            class="w-full px-2.5 py-1.5 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>

        <!-- Table groups -->
        <div class="flex-1 overflow-y-auto">
          <template v-for="cat in (['financial', 'investments', 'property', 'planning', 'system'] as TableCategory[])" :key="cat">
            <div v-if="groupedTables[cat].length > 0">
              <!-- Category header -->
              <div class="px-3 py-1.5 flex items-center gap-2 sticky top-0 bg-gray-50 dark:bg-gray-800/60 z-10">
                <span :class="['w-2 h-2 rounded-full flex-shrink-0', categoryColors[cat].dot]"></span>
                <span class="text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">{{ categoryLabels[cat] }}</span>
                <span class="text-[10px] text-gray-300 dark:text-gray-600">({{ groupedTables[cat].length }})</span>
              </div>
              <!-- Tables in group -->
              <ul>
                <li
                  v-for="t in groupedTables[cat]"
                  :key="t.name"
                  @click="selectTable(t.name)"
                  :class="[
                    'px-3 py-2 cursor-pointer transition-colors',
                    selectedTable === t.name
                      ? 'bg-indigo-50 dark:bg-indigo-950/60'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800/40'
                  ]"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span
                      :class="[
                        'text-xs font-medium truncate',
                        selectedTable === t.name
                          ? 'text-indigo-700 dark:text-indigo-300'
                          : 'text-gray-800 dark:text-gray-200'
                      ]"
                    >{{ t.name }}</span>
                    <div class="flex items-center gap-1.5 flex-shrink-0">
                      <button
                        @click.stop="openPreviewModal(t.name)"
                        class="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                        title="Preview data"
                      >
                        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/>
                        </svg>
                      </button>
                      <span class="text-[10px] text-gray-400 dark:text-gray-500 tabular-nums">
                        {{ t.row_count.toLocaleString() }}
                      </span>
                    </div>
                  </div>
                  <p v-if="t.description" class="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5 line-clamp-2 leading-tight">
                    {{ t.description }}
                  </p>
                </li>
              </ul>
            </div>
          </template>
        </div>
      </aside>

      <!-- ═══ Center Panel ═══ -->
      <div class="flex-1 min-w-0 flex flex-col gap-4 min-h-0">

        <!-- Center content area -->
        <div class="flex-1 min-h-0 flex flex-col bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">

          <!-- Tab bar -->
          <div class="flex items-center justify-between px-4 py-2 border-b border-gray-100 dark:border-gray-800 flex-shrink-0">
            <div class="flex gap-1">
              <button
                @click="centerMode = 'schema'"
                :class="[
                  'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                  centerMode === 'schema'
                    ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                ]"
              >
                Schema
              </button>
              <button
                @click="centerMode = 'query'"
                :class="[
                  'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                  centerMode === 'query'
                    ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                ]"
              >
                Query
              </button>
              <button
                @click="centerMode = 'access'"
                :class="[
                  'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                  centerMode === 'access'
                    ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                ]"
              >
                Access
              </button>
            </div>
            <div class="flex items-center gap-2">
              <InfoTooltip
                text="<strong>Schema View</strong><br>Visual map of your database tables and their relationships. Click a card to select it; click again to preview its data. Use the table icon to open data preview. Primary keys shown in gold, foreign keys in blue."
              />
            </div>
          </div>

          <!-- Schema mode (ERD) -->
          <div
            v-if="centerMode === 'schema'"
            ref="erdContainer"
            class="flex-1 overflow-hidden bg-gray-50 dark:bg-gray-950/50 relative"
            :style="{ cursor: canvasCursor }"
            @wheel.prevent="onWheel"
            @pointerdown="onPointerDown"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointerleave="onPointerUp"
          >
            <!-- Zoom controls -->
            <div class="absolute top-2 right-2 flex gap-1 z-10">
              <button @click="zoomIn" class="p-1.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-xs font-medium text-gray-600 dark:text-gray-300" title="Zoom in">+</button>
              <button @click="zoomOut" class="p-1.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-xs font-medium text-gray-600 dark:text-gray-300" title="Zoom out">&minus;</button>
              <button @click="zoomFit" class="p-1.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-[10px] font-medium text-gray-600 dark:text-gray-300" title="Fit to view">Fit</button>
              <button @click="zoomReset" class="p-1.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-[10px] font-medium text-gray-600 dark:text-gray-300" title="Reset zoom">1:1</button>
              <button @click="toggleFullscreen" class="p-1.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-xs text-gray-600 dark:text-gray-300" title="Toggle fullscreen">&#x26F6;</button>
            </div>
            <!-- Zoom percentage indicator -->
            <div class="absolute bottom-2 right-2 z-10 text-[10px] text-gray-400 dark:text-gray-500 tabular-nums select-none">
              {{ Math.round(zoom * 100) }}%
            </div>
            <svg :width="svgWidth" :height="svgHeight" class="block" :style="{ transform: canvasTransform, transformOrigin: '0 0' }">
              <!-- Relationship lines (orthogonal) -->
              <defs>
                <marker id="arrow-active" viewBox="0 0 8 8" refX="8" refY="4" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
                  <path d="M 0 0.5 L 8 4 L 0 7.5 Z" fill="#6366f1"/>
                </marker>
                <marker id="arrow-inactive" viewBox="0 0 8 8" refX="8" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 1 L 8 4 L 0 7 Z" fill="#94a3b8" fill-opacity="0.5"/>
                </marker>
                <!-- Glow filter for active lines -->
                <filter id="edge-glow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="blur"/>
                  <feMerge>
                    <feMergeNode in="blur"/>
                    <feMergeNode in="SourceGraphic"/>
                  </feMerge>
                </filter>
              </defs>

              <!-- Inactive edges (rendered first, underneath) -->
              <g>
                <path
                  v-for="(ep, i) in inactiveEdgePaths"
                  :key="'edge-inactive-' + i"
                  :d="ep.path"
                  fill="none"
                  :stroke-width="1"
                  stroke="#94a3b8"
                  :stroke-opacity="selectedTable ? 0.12 : 0.35"
                  marker-end="url(#arrow-inactive)"
                  class="transition-all duration-300"
                >
                  <title>{{ ep.edge.from_table }}.{{ ep.edge.from_column }} → {{ ep.edge.to_table }}.{{ ep.edge.to_column }}</title>
                </path>
              </g>

              <!-- Active edges (rendered on top, highlighted) -->
              <g>
                <path
                  v-for="(ep, i) in activeEdgePaths"
                  :key="'edge-active-' + i"
                  :d="ep.path"
                  fill="none"
                  stroke-width="2.5"
                  stroke="#6366f1"
                  stroke-opacity="1"
                  marker-end="url(#arrow-active)"
                  filter="url(#edge-glow)"
                  class="transition-all duration-300"
                >
                  <title>{{ ep.edge.from_table }}.{{ ep.edge.from_column }} → {{ ep.edge.to_table }}.{{ ep.edge.to_column }}</title>
                </path>
              </g>

              <!-- Table cards -->
              <g v-for="cl in cardLayouts" :key="cl.table.name" :data-table="cl.table.name">
                <!-- Card background -->
                <rect
                  :x="cl.x" :y="cl.y" :width="cl.w" :height="cl.h"
                  rx="8" ry="8"
                  :class="{
                    'cursor-pointer': true,
                  }"
                  :fill="selectedTable === cl.table.name ? (isDark ? '#1e1b4b' : '#eef2ff') : (isDark ? '#111827' : '#ffffff')"
                  :stroke="selectedTable === cl.table.name ? '#6366f1' : relatedTables.has(cl.table.name) ? '#818cf8' : (isDark ? '#374151' : '#e5e7eb')"
                  :stroke-width="selectedTable === cl.table.name ? 2 : 1"
                  @click="clickErdCard(cl.table.name)"
                  class="transition-all duration-200"
                />

                <!-- Header group (keeps table tooltip scoped to header only) -->
                <g>
                  <title v-if="cl.table.description">{{ cl.table.name }}: {{ cl.table.description }}</title>
                  <rect
                    :x="cl.x" :y="cl.y" :width="cl.w" :height="CARD_HEADER_H"
                    :rx="8" :ry="8"
                    :fill="selectedTable === cl.table.name ? '#6366f1' : {
                      financial: '#3b82f6',
                      investments: '#10b981',
                      property: '#f59e0b',
                      planning: '#8b5cf6',
                      system: '#6b7280'
                    }[classifyTable(cl.table.name)]"
                    :fill-opacity="selectedTable === cl.table.name ? 1 : 0.85"
                    @click="clickErdCard(cl.table.name)"
                    class="cursor-pointer"
                  />
                  <rect
                    :x="cl.x" :y="cl.y + CARD_HEADER_H - 8" :width="cl.w" :height="8"
                    :fill="selectedTable === cl.table.name ? '#6366f1' : {
                      financial: '#3b82f6',
                      investments: '#10b981',
                      property: '#f59e0b',
                      planning: '#8b5cf6',
                      system: '#6b7280'
                    }[classifyTable(cl.table.name)]"
                    :fill-opacity="selectedTable === cl.table.name ? 1 : 0.85"
                    @click="clickErdCard(cl.table.name)"
                    class="cursor-pointer"
                  />
                </g>

                <!-- Table name -->
                <text
                  :x="cl.x + 10" :y="cl.y + CARD_HEADER_H / 2 + 1"
                  dominant-baseline="middle"
                  fill="white"
                  font-size="12"
                  font-weight="600"
                  font-family="ui-monospace, monospace"
                  @click="clickErdCard(cl.table.name)"
                  class="cursor-pointer select-none"
                >{{ cl.table.name }}</text>

                <!-- Preview data button -->
                <g
                  @click.stop="openPreviewModal(cl.table.name)"
                  class="cursor-pointer"
                  :transform="`translate(${cl.x + cl.w - 58}, ${cl.y + CARD_HEADER_H / 2 - 6})`"
                >
                  <title>Preview data</title>
                  <rect x="-2" y="-2" width="16" height="16" fill="transparent" />
                  <rect x="0" y="0" width="12" height="12" rx="1.5" fill="none" stroke="rgba(255,255,255,0.7)" stroke-width="1.2"/>
                  <line x1="0" y1="4" x2="12" y2="4" stroke="rgba(255,255,255,0.7)" stroke-width="1"/>
                  <line x1="0" y1="8" x2="12" y2="8" stroke="rgba(255,255,255,0.7)" stroke-width="1"/>
                  <line x1="5" y1="0" x2="5" y2="12" stroke="rgba(255,255,255,0.7)" stroke-width="1"/>
                </g>

                <!-- Row count badge -->
                <text
                  :x="cl.x + cl.w - 10" :y="cl.y + CARD_HEADER_H / 2 + 1"
                  dominant-baseline="middle"
                  text-anchor="end"
                  fill="rgba(255,255,255,0.7)"
                  font-size="10"
                  font-family="ui-sans-serif, system-ui, sans-serif"
                  @click="clickErdCard(cl.table.name)"
                  class="cursor-pointer select-none"
                >{{ cl.table.row_count.toLocaleString() }}</text>

                <!-- Columns -->
                <g v-for="(col, ci) in cl.table.columns" :key="col.name" class="erd-col-row">
                  <title v-if="col.description">{{ col.name }}: {{ col.description }}</title>
                  <!-- Hover highlight background -->
                  <rect
                    :x="cl.x + 1"
                    :y="cl.y + CARD_HEADER_H + CARD_PAD_Y + ci * CARD_ROW_H"
                    :width="cl.w - 2"
                    :height="CARD_ROW_H"
                    class="erd-col-bg"
                    :rx="3"
                  />
                  <text
                    :x="cl.x + 10"
                    :y="cl.y + CARD_HEADER_H + CARD_PAD_Y + ci * CARD_ROW_H + CARD_ROW_H / 2 + 1"
                    dominant-baseline="middle"
                    :fill="col.primary_key ? '#d97706' : isColumnFk(cl.table.name, col.name) ? '#6366f1' : (isDark ? '#d1d5db' : '#374151')"
                    :font-weight="col.primary_key ? '600' : '400'"
                    font-size="11"
                    font-family="ui-monospace, monospace"
                    class="pointer-events-none"
                  >
                    <tspan v-if="col.primary_key" font-size="10">&#x1F511; </tspan>
                    <tspan v-else-if="isColumnFk(cl.table.name, col.name)" font-size="10">&#x1F517; </tspan>
                    {{ col.name }}
                  </text>
                  <!-- Type badge -->
                  <text
                    :x="cl.x + cl.w - (col.description ? 22 : 10)"
                    :y="cl.y + CARD_HEADER_H + CARD_PAD_Y + ci * CARD_ROW_H + CARD_ROW_H / 2 + 1"
                    dominant-baseline="middle"
                    text-anchor="end"
                    :fill="isDark ? '#6b7280' : '#9ca3af'"
                    font-size="10"
                    font-family="ui-sans-serif, system-ui, sans-serif"
                    class="pointer-events-none"
                  >{{ formatType(col.type) }}</text>

                  <!-- Nullable indicator -->
                  <text
                    v-if="col.nullable"
                    :x="cl.x + cl.w - (col.description ? 22 : 10) - (formatType(col.type).length * 6) - 6"
                    :y="cl.y + CARD_HEADER_H + CARD_PAD_Y + ci * CARD_ROW_H + CARD_ROW_H / 2 + 1"
                    dominant-baseline="middle"
                    text-anchor="end"
                    :fill="isDark ? '#4b5563' : '#d1d5db'"
                    font-size="9"
                    font-family="ui-sans-serif, system-ui, sans-serif"
                    class="pointer-events-none"
                  >?</text>

                  <!-- Info icon (visible on hover when description exists) -->
                  <g v-if="col.description" class="erd-col-info pointer-events-none">
                    <circle
                      :cx="cl.x + cl.w - 11"
                      :cy="cl.y + CARD_HEADER_H + CARD_PAD_Y + ci * CARD_ROW_H + CARD_ROW_H / 2 + 1"
                      r="6"
                      :fill="isDark ? '#374151' : '#e5e7eb'"
                    />
                    <text
                      :x="cl.x + cl.w - 11"
                      :y="cl.y + CARD_HEADER_H + CARD_PAD_Y + ci * CARD_ROW_H + CARD_ROW_H / 2 + 1.5"
                      text-anchor="middle"
                      dominant-baseline="middle"
                      :fill="isDark ? '#9ca3af' : '#6b7280'"
                      font-size="8"
                      font-weight="600"
                      font-family="ui-sans-serif, system-ui, sans-serif"
                    >i</text>
                  </g>
                </g>
              </g>
            </svg>
          </div>

          <!-- Query mode (SQL Runner) -->
          <div v-else-if="centerMode === 'query'" class="flex-1 flex flex-col min-h-0">
            <!-- Input area -->
            <div class="px-3 py-2 flex-shrink-0">
              <div class="relative border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden focus-within:ring-1 focus-within:ring-indigo-500 focus-within:border-indigo-500">
                <!-- Highlight layer (behind textarea) -->
                <pre
                  class="sql-highlight-layer sql-block absolute inset-0 px-3 py-2 text-[12px] leading-[1.6] font-mono whitespace-pre-wrap break-words overflow-auto pointer-events-none bg-gray-50 dark:bg-gray-950 m-0"
                  aria-hidden="true"
                ><code v-html="highlightedSqlText"></code></pre>
                <!-- Textarea (transparent text, visible caret) -->
                <textarea
                  ref="sqlEditorRef"
                  v-model="sqlText"
                  @keydown="handleSqlKeydown"
                  @scroll="syncScroll"
                  placeholder="SELECT * FROM accounts LIMIT 10"
                  spellcheck="false"
                  class="relative w-full min-h-[80px] max-h-[200px] px-3 py-2 text-[12px] leading-[1.6] font-mono bg-transparent text-transparent caret-gray-800 dark:caret-gray-200 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none resize-y z-10"
                ></textarea>
              </div>
              <div class="flex items-center justify-between mt-1.5">
                <span class="text-[10px] text-gray-400 dark:text-gray-500">
                  <kbd class="px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-[9px] font-mono">&#x2318;Enter</kbd> to run
                </span>
                <button
                  @click="runSql"
                  :disabled="sqlRunning || !sqlText.trim()"
                  :class="[
                    'px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors',
                    sqlRunning || !sqlText.trim()
                      ? 'bg-gray-200 dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed'
                      : 'bg-indigo-600 hover:bg-indigo-700 text-white'
                  ]"
                >
                  <span v-if="sqlRunning" class="flex items-center gap-1.5">
                    <svg class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                    Running...
                  </span>
                  <span v-else>Run</span>
                </button>
              </div>
            </div>

            <!-- SQL error -->
            <div v-if="sqlError" class="px-3 py-2 flex-shrink-0">
              <div class="px-3 py-2 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg text-xs text-red-600 dark:text-red-400 font-mono break-all">
                {{ sqlError }}
              </div>
            </div>

            <!-- SQL results -->
            <div v-if="sqlResult" class="flex-1 overflow-auto min-h-0 px-3 pb-2">
              <div class="flex items-center justify-between px-1 py-1 mb-1">
                <span class="text-[10px] text-gray-400 dark:text-gray-500 tabular-nums">
                  {{ sqlResult.row_count }} row{{ sqlResult.row_count !== 1 ? 's' : '' }}
                  <span v-if="sqlResult.query" class="ml-2 text-gray-300 dark:text-gray-600">|</span>
                  <span v-if="sqlResult.query" class="ml-2">{{ sqlResult.columns.length }} col{{ sqlResult.columns.length !== 1 ? 's' : '' }}</span>
                </span>
              </div>
              <div class="border border-gray-200 dark:border-gray-700 rounded-lg overflow-x-auto overflow-y-auto">
                <table class="text-xs min-w-full">
                  <thead class="sticky top-0 z-10">
                    <tr class="bg-gray-50 dark:bg-gray-800">
                      <th
                        v-for="col in sqlResult.columns"
                        :key="col"
                        class="px-3 py-2 text-left font-semibold text-gray-600 dark:text-gray-300 whitespace-nowrap border-b border-gray-200 dark:border-gray-700"
                      >{{ col }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(row, idx) in sqlResult.rows"
                      :key="idx"
                      class="border-b border-gray-50 dark:border-gray-800/50 hover:bg-gray-50/60 dark:hover:bg-gray-800/30"
                    >
                      <td
                        v-for="col in sqlResult.columns"
                        :key="col"
                        class="px-3 py-1.5 text-gray-700 dark:text-gray-300 whitespace-nowrap max-w-[300px] truncate font-mono"
                        :title="formatCellValue(row[col])"
                      >{{ formatCellValue(row[col]) }}</td>
                    </tr>
                    <tr v-if="sqlResult.rows.length === 0">
                      <td :colspan="sqlResult.columns.length" class="px-4 py-4 text-center text-gray-400 dark:text-gray-500">
                        Query returned no rows
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Empty state -->
            <div v-if="!sqlResult && !sqlError && !sqlRunning" class="flex-1 flex items-center justify-center">
              <p class="text-xs text-gray-300 dark:text-gray-600">Press Cmd+Enter to run a query</p>
            </div>
          </div>

          <!-- Access mode -->
          <div v-else-if="centerMode === 'access'" class="flex-1 min-h-0 overflow-y-auto">
            <div class="max-w-3xl mx-auto px-6 py-6 space-y-6">

              <!-- Create credential form -->
              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">Create Database Credential</h3>
                <p class="text-xs text-gray-400 mb-4">Generate Postgres credentials to connect with external tools like psql, DBeaver, Excel, or Python.</p>

                <div class="flex items-end gap-3">
                  <div class="flex-1">
                    <label class="block text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1">Name</label>
                    <input
                      v-model="credName"
                      type="text"
                      placeholder="e.g. DBeaver, Python notebook"
                      class="w-full px-3 py-2 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400"
                    />
                  </div>
                  <div class="w-40">
                    <label class="block text-[11px] font-medium text-gray-500 dark:text-gray-400 mb-1">Access Level</label>
                    <select
                      v-model="credAccessLevel"
                      class="w-full px-3 py-2 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400"
                    >
                      <option value="read">Read-only</option>
                      <option value="readwrite">Read-write</option>
                    </select>
                  </div>
                  <button
                    @click="createCredential"
                    :disabled="!credName.trim() || credCreating"
                    class="px-4 py-2 text-xs font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
                  >
                    {{ credCreating ? 'Creating...' : 'Create Credential' }}
                  </button>
                </div>
                <p v-if="credError" class="mt-2 text-xs text-red-500">{{ credError }}</p>
              </div>

              <!-- Credential created notice (credentials shown in modal) -->
              <div v-if="newCredential" class="bg-emerald-50 dark:bg-emerald-950/30 rounded-xl border border-emerald-200 dark:border-emerald-800 p-4 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <svg class="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                  </svg>
                  <span class="text-xs text-emerald-700 dark:text-emerald-300 font-medium">Credential created. Review the details in the dialog.</span>
                </div>
              </div>

              <!-- Active credentials list -->
              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Active Credentials</h3>

                <div v-if="credLoading" class="flex justify-center py-6">
                  <div class="animate-spin rounded-full h-5 w-5 border-b-2 border-indigo-500"></div>
                </div>

                <div v-else-if="credentials.length === 0" class="text-center py-6">
                  <p class="text-xs text-gray-400">No database credentials yet. Create one above to get started.</p>
                </div>

                <table v-else class="w-full text-xs">
                  <thead>
                    <tr class="border-b border-gray-100 dark:border-gray-800">
                      <th class="text-left py-2 pr-4 font-medium text-gray-500 dark:text-gray-400">Name</th>
                      <th class="text-left py-2 pr-4 font-medium text-gray-500 dark:text-gray-400">Username</th>
                      <th class="text-left py-2 pr-4 font-medium text-gray-500 dark:text-gray-400">Access</th>
                      <th class="text-left py-2 pr-4 font-medium text-gray-500 dark:text-gray-400">Created</th>
                      <th class="text-right py-2 font-medium text-gray-500 dark:text-gray-400"></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="cred in credentials" :key="cred.id" class="border-b border-gray-50 dark:border-gray-800/50">
                      <td class="py-2.5 pr-4 text-gray-900 dark:text-white font-medium">{{ cred.name }}</td>
                      <td class="py-2.5 pr-4 font-mono text-gray-600 dark:text-gray-400">{{ cred.pg_username }}</td>
                      <td class="py-2.5 pr-4">
                        <span :class="[
                          'inline-flex px-2 py-0.5 rounded-full text-[10px] font-medium',
                          cred.access_level === 'read'
                            ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300'
                            : 'bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-300'
                        ]">{{ cred.access_level === 'read' ? 'Read-only' : 'Read-write' }}</span>
                      </td>
                      <td class="py-2.5 pr-4 text-gray-500 dark:text-gray-400">{{ formatCredDate(cred.created_at) }}</td>
                      <td class="py-2.5 text-right">
                        <button
                          v-if="cred.is_active"
                          @click="revokeCredential(cred.id)"
                          :disabled="credRevoking === cred.id"
                          class="px-2.5 py-1 text-[10px] font-medium rounded-lg border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 disabled:opacity-40 transition-colors"
                        >
                          {{ credRevoking === cred.id ? 'Revoking...' : 'Revoke' }}
                        </button>
                        <span v-else class="text-[10px] text-gray-400">Revoked</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <!-- Connection examples (always visible) -->
              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">Connection Examples</h3>
                <p class="text-xs text-gray-400 mb-4">Replace the placeholders with your credential details from above.</p>

                <div class="space-y-4">
                  <div>
                    <h4 class="text-[11px] font-semibold text-gray-700 dark:text-gray-300 mb-1.5">psql (Terminal)</h4>
                    <code class="block text-[11px] bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2.5 text-gray-700 dark:text-gray-300 font-mono break-all">psql "postgresql://USERNAME:PASSWORD@HOST:5432/tallied?options=-csearch_path%3DSCHEMA"</code>
                  </div>

                  <div>
                    <h4 class="text-[11px] font-semibold text-gray-700 dark:text-gray-300 mb-1.5">Python (SQLAlchemy / pandas)</h4>
                    <pre class="text-[11px] bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2.5 text-gray-700 dark:text-gray-300 font-mono break-all whitespace-pre-wrap">from sqlalchemy import create_engine
import pandas as pd

engine = create_engine("postgresql://USERNAME:PASSWORD@HOST:5432/tallied?options=-csearch_path%3DSCHEMA")
df = pd.read_sql("SELECT * FROM accounts", engine)</pre>
                  </div>

                  <div>
                    <h4 class="text-[11px] font-semibold text-gray-700 dark:text-gray-300 mb-1.5">DBeaver / DataGrip</h4>
                    <div class="text-[11px] bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2.5 text-gray-700 dark:text-gray-300 space-y-1">
                      <p>1. New PostgreSQL connection</p>
                      <p>2. Enter <span class="font-mono">Host</span>, <span class="font-mono">Port</span>, <span class="font-mono">Database</span>, <span class="font-mono">Username</span>, <span class="font-mono">Password</span> from your credential</p>
                      <p>3. In Connection Properties, set <span class="font-mono">search_path</span> to your tenant schema</p>
                    </div>
                  </div>

                  <div>
                    <h4 class="text-[11px] font-semibold text-gray-700 dark:text-gray-300 mb-1.5">Excel / Power BI (ODBC)</h4>
                    <div class="text-[11px] bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2.5 text-gray-700 dark:text-gray-300 space-y-1">
                      <p>1. Install the <a href="https://www.postgresql.org/ftp/odbc/" target="_blank" class="text-indigo-500 hover:text-indigo-600 underline">PostgreSQL ODBC driver</a></p>
                      <p>2. Data &rarr; Get Data &rarr; From ODBC / From Database &rarr; PostgreSQL</p>
                      <p>3. Server: <span class="font-mono">HOST:5432</span>, Database: <span class="font-mono">tallied</span></p>
                      <p>4. Enter your credential username and password</p>
                    </div>
                  </div>
                </div>
              </div>

            </div>
          </div>

        </div>

      </div>
    </div>

    <!-- ═══ Data Preview Modal ═══ -->
    <!-- Credential created modal -->
    <Teleport to="body">
      <div v-if="showCredentialModal" class="fixed inset-0 z-[100] flex items-center justify-center">
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="closeCredentialModal"></div>

        <!-- Modal -->
        <div class="relative w-[90vw] max-w-2xl max-h-[85vh] bg-white dark:bg-gray-900 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden">
          <!-- Header -->
          <div class="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
            <div class="flex items-center gap-2.5">
              <svg class="w-5 h-5 text-amber-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Database Credentials Created</h3>
            </div>
            <button
              @click="closeCredentialModal"
              class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            >
              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 6L6 18"/><path d="M6 6l12 12"/>
              </svg>
            </button>
          </div>

          <!-- Warning banner -->
          <div class="px-5 py-3 bg-amber-50 dark:bg-amber-950/30 border-b border-amber-200 dark:border-amber-800 flex-shrink-0">
            <p class="text-xs text-amber-800 dark:text-amber-200 font-semibold">Save these credentials now. They will not be shown again after you close this dialog.</p>
          </div>

          <!-- Content -->
          <div v-if="newCredential" class="flex-1 overflow-y-auto px-5 py-4 space-y-4">
            <!-- Connection details -->
            <div class="space-y-2">
              <h4 class="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Connection Details</h4>
              <div class="grid grid-cols-2 gap-2">
                <div v-for="item in [
                  { label: 'Username', value: newCredential.pg_username, key: 'username' },
                  { label: 'Password', value: newCredential.password, key: 'password' },
                  { label: 'Host', value: newCredential.host, key: 'host' },
                  { label: 'Port', value: String(newCredential.port), key: 'port' },
                  { label: 'Database', value: newCredential.database, key: 'database' },
                  { label: 'Schema', value: newCredential.schema_name, key: 'schema' },
                ]" :key="item.key" class="flex items-center gap-2 bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2">
                  <div class="flex-1 min-w-0">
                    <div class="text-[10px] font-medium text-gray-400 dark:text-gray-500">{{ item.label }}</div>
                    <div class="text-[11px] font-mono text-gray-800 dark:text-gray-200 truncate">{{ item.value }}</div>
                  </div>
                  <button
                    @click="copyToClipboard(item.value, item.key)"
                    class="flex-shrink-0 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                    :title="'Copy ' + item.label"
                  >
                    <svg v-if="copiedField !== item.key" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                    </svg>
                    <svg v-else class="w-3.5 h-3.5 text-emerald-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                  </button>
                </div>
              </div>
            </div>

            <!-- Connection string -->
            <div>
              <h4 class="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">Connection String</h4>
              <div class="flex items-center gap-2">
                <code class="flex-1 block text-[11px] bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 text-gray-800 dark:text-gray-200 font-mono break-all select-all">{{ newCredential.connection_string }}</code>
                <button
                  @click="copyToClipboard(newCredential!.connection_string, 'connstr')"
                  class="flex-shrink-0 p-1.5 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                  title="Copy connection string"
                >
                  <svg v-if="copiedField !== 'connstr'" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                  </svg>
                  <svg v-else class="w-3.5 h-3.5 text-emerald-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                </button>
              </div>
            </div>

            <!-- Code examples -->
            <div class="space-y-3">
              <h4 class="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Code Examples</h4>

              <!-- psql -->
              <div>
                <div class="flex items-center justify-between mb-1">
                  <span class="text-[11px] font-medium text-gray-600 dark:text-gray-400">psql</span>
                  <button
                    @click="copyToClipboard('psql &quot;' + newCredential!.connection_string + '&quot;', 'psql')"
                    class="flex-shrink-0 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                    title="Copy psql command"
                  >
                    <svg v-if="copiedField !== 'psql'" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                    </svg>
                    <svg v-else class="w-3.5 h-3.5 text-emerald-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                  </button>
                </div>
                <code class="block text-[11px] bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 text-gray-800 dark:text-gray-200 font-mono break-all select-all">psql "{{ newCredential.connection_string }}"</code>
              </div>

              <!-- Python -->
              <div>
                <div class="flex items-center justify-between mb-1">
                  <span class="text-[11px] font-medium text-gray-600 dark:text-gray-400">Python (SQLAlchemy)</span>
                  <button
                    @click="copyToClipboard('from sqlalchemy import create_engine\nengine = create_engine(&quot;' + newCredential!.connection_string + '&quot;)', 'python')"
                    class="flex-shrink-0 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                    title="Copy Python snippet"
                  >
                    <svg v-if="copiedField !== 'python'" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                    </svg>
                    <svg v-else class="w-3.5 h-3.5 text-emerald-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                  </button>
                </div>
                <code class="block text-[11px] bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 text-gray-800 dark:text-gray-200 font-mono break-all select-all whitespace-pre-wrap">from sqlalchemy import create_engine
engine = create_engine("{{ newCredential.connection_string }}")</code>
              </div>
            </div>
          </div>

          <!-- Footer -->
          <div class="px-5 py-3 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between flex-shrink-0">
            <button
              @click="downloadCredentialsMd"
              class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              Download as .md
            </button>
            <button
              @click="closeCredentialModal"
              class="px-4 py-1.5 text-xs font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Data preview modal -->
    <Teleport to="body">
      <div v-if="showPreviewModal" class="fixed inset-0 z-[100] flex items-center justify-center">
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="closePreviewModal"></div>

        <!-- Modal -->
        <div class="relative w-[90vw] max-w-5xl max-h-[85vh] bg-white dark:bg-gray-900 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden">
          <!-- Header -->
          <div class="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
            <div class="flex items-center gap-3">
              <svg class="w-4 h-4 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/>
              </svg>
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ previewModalTable }}</h3>
              <span v-if="previewData" class="text-[10px] text-gray-400 dark:text-gray-500 tabular-nums">
                {{ previewData.total.toLocaleString() }} rows
              </span>
            </div>
            <button
              @click="closePreviewModal"
              class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            >
              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 6L6 18"/><path d="M6 6l12 12"/>
              </svg>
            </button>
          </div>

          <!-- Table description -->
          <div v-if="previewTableSchema?.description" class="px-5 py-2 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
            <p class="text-[11px] text-gray-500 dark:text-gray-400 leading-relaxed">{{ previewTableSchema.description }}</p>
          </div>

          <!-- Loading -->
          <div v-if="previewLoading" class="flex items-center justify-center py-16">
            <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500"></div>
          </div>

          <!-- Error -->
          <div v-else-if="previewError" class="flex items-center justify-center py-16">
            <p class="text-sm text-red-500">{{ previewError }}</p>
          </div>

          <!-- Data table -->
          <div v-else-if="previewData" class="flex-1 overflow-auto min-h-0">
            <table class="w-full text-xs">
              <thead class="sticky top-0 z-10">
                <tr class="bg-gray-50 dark:bg-gray-800/80">
                  <th
                    v-for="col in previewData.columns"
                    :key="col"
                    :class="[
                      'px-3 py-2.5 text-left font-semibold whitespace-nowrap border-b border-gray-200 dark:border-gray-700 group/col',
                      isColumnPk(previewModalTable!, col) ? 'text-amber-600 dark:text-amber-400' :
                      isColumnFk(previewModalTable!, col) ? 'text-indigo-600 dark:text-indigo-400' :
                      'text-gray-600 dark:text-gray-300'
                    ]"
                  >
                    <span class="flex items-center gap-1">
                      <span v-if="isColumnPk(previewModalTable!, col)" class="text-[10px]">&#x1F511;</span>
                      <span v-if="isColumnFk(previewModalTable!, col)" class="text-[10px]">&#x1F517;</span>
                      {{ col }}
                      <span
                        v-if="previewTableSchema"
                        class="ml-1 text-[9px] font-normal px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500"
                      >{{ formatType(previewTableSchema.columns.find(c => c.name === col)?.type ?? '') }}</span>
                      <span
                        v-if="previewTableSchema?.columns.find(c => c.name === col)?.description"
                        class="relative ml-0.5 inline-flex items-center"
                      >
                        <span class="w-3.5 h-3.5 inline-flex items-center justify-center rounded-full bg-gray-200 dark:bg-gray-600 text-gray-500 dark:text-gray-300 text-[8px] font-bold cursor-help peer">i</span>
                        <span class="absolute left-1/2 -translate-x-1/2 bottom-full mb-1.5 hidden peer-hover:block w-max max-w-[260px] px-2.5 py-1.5 text-[10px] font-normal leading-snug text-white bg-gray-800 dark:bg-gray-700 rounded-lg shadow-lg z-50 whitespace-normal">
                          {{ previewTableSchema?.columns.find(c => c.name === col)?.description }}
                        </span>
                      </span>
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, idx) in previewData.rows"
                  :key="idx"
                  class="border-b border-gray-50 dark:border-gray-800/50 hover:bg-gray-50/60 dark:hover:bg-gray-800/30 transition-colors"
                >
                  <td
                    v-for="col in previewData.columns"
                    :key="col"
                    class="px-3 py-2 whitespace-nowrap max-w-[240px] truncate"
                    :title="formatCellValue(row[col])"
                  >
                    <button
                      v-if="previewFkColumns.has(col) && row[col] != null"
                      @click.stop="jumpToFk(previewFkColumns.get(col)!.table, previewFkColumns.get(col)!.column, row[col])"
                      class="text-indigo-600 dark:text-indigo-400 hover:underline font-medium"
                    >{{ formatCellValue(row[col]) }}</button>
                    <span v-else :class="row[col] === null || row[col] === undefined ? 'text-gray-300 dark:text-gray-600 italic' : 'text-gray-700 dark:text-gray-300'">
                      {{ formatCellValue(row[col]) }}
                    </span>
                  </td>
                </tr>
                <tr v-if="previewData.rows.length === 0">
                  <td :colspan="previewData.columns.length" class="px-4 py-8 text-center text-gray-400 dark:text-gray-500 text-sm">
                    No rows found
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Pagination -->
          <div v-if="previewData && previewData.total > PAGE_SIZE" class="flex items-center justify-between px-5 py-2.5 border-t border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 flex-shrink-0">
            <button
              @click="prevPage"
              :disabled="previewOffset === 0"
              :class="[
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                previewOffset === 0
                  ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                  : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
              ]"
            >&larr; Prev</button>
            <span class="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
              {{ previewOffset + 1 }}&ndash;{{ Math.min(previewOffset + PAGE_SIZE, previewData.total) }}
              of {{ previewData.total.toLocaleString() }}
              <span class="text-gray-300 dark:text-gray-600 mx-1">|</span>
              Page {{ previewCurrentPage }} / {{ previewTotalPages }}
            </span>
            <button
              @click="nextPage"
              :disabled="previewOffset + PAGE_SIZE >= previewData.total"
              :class="[
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                previewOffset + PAGE_SIZE >= previewData.total
                  ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                  : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
              ]"
            >Next &rarr;</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style>
/* ERD column row hover effect (unscoped so dark mode works) */
.erd-col-bg {
  fill: transparent;
  transition: fill 0.15s;
  cursor: default;
}
.erd-col-row:hover .erd-col-bg {
  fill: rgba(99, 102, 241, 0.08);
}
.dark .erd-col-row:hover .erd-col-bg {
  fill: rgba(99, 102, 241, 0.15);
}

/* Info icon — hidden by default, shown on row hover */
.erd-col-info {
  opacity: 0;
  transition: opacity 0.15s;
}
.erd-col-row:hover .erd-col-info {
  opacity: 1;
}

/* SQL syntax highlighting */
.sql-block .sql-keyword { color: #8b5cf6; font-weight: 600; }
.sql-block .sql-function { color: #0891b2; }
.sql-block .sql-string { color: #16a34a; }
.sql-block .sql-number { color: #d97706; }
.sql-block .sql-comment { color: #9ca3af; font-style: italic; }
.sql-block .sql-operator { color: #6b7280; }

.dark .sql-block .sql-keyword { color: #a78bfa; }
.dark .sql-block .sql-function { color: #22d3ee; }
.dark .sql-block .sql-string { color: #4ade80; }
.dark .sql-block .sql-number { color: #fbbf24; }
.dark .sql-block .sql-comment { color: #6b7280; }
.dark .sql-block .sql-operator { color: #9ca3af; }

/* SQL editor overlay alignment */
.sql-highlight-layer {
  word-break: break-word;
  overflow-wrap: break-word;
}
</style>
