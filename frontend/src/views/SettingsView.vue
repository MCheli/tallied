<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../api/client'
import { useFormatters } from '../composables/useFormatters'
import type { AccountWithBalance, W2Record } from '../types'

const { currency } = useFormatters()

// Tab management
// Note: 'monarch' tab is hidden but the underlying script state, helpers,
// and template block are kept in case Monarch ships a real API integration
// in the future. Routes (/api/v1/monarch/*) and the scheduler dispatch
// remain wired up — only the user-facing tab is gone.
type Tab = 'accounts' | 'income' | 'plaid' | 'monarch' | 'simplefin' | 'email' | 'import'
const activeTab = ref<Tab>('accounts')
const tabs: { key: Tab; label: string }[] = [
  { key: 'accounts', label: 'Accounts' },
  { key: 'income', label: 'Income' },
  { key: 'plaid', label: 'Plaid' },
  { key: 'simplefin', label: 'SimpleFIN' },
  { key: 'email', label: 'Email' },
  { key: 'import', label: 'Import' },
]

// ── Accounts ──
const accounts = ref<AccountWithBalance[]>([])
const accountsLoading = ref(false)
const editingAccountId = ref<string | null>(null)
const showNewAccountForm = ref(false)

const accountTypes = ['cash', 'investment_401k', 'investment_stock', 'real_estate', 'loan_mortgage', 'loan_student', 'credit_card']
const displayGroups = ['Cash', 'Investments', 'Retirement', 'Home Equity', 'Credit Cards', 'Other Loans']

function sourceLabel(source: string): string {
  return ({
    monarch: 'Monarch',
    simplefin: 'SimpleFIN',
    plaid: 'Plaid',
    manual: 'Manual',
  } as Record<string, string>)[source] || source
}

function sourceBadgeClass(source: string): string {
  return ({
    monarch: 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400',
    simplefin: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400',
    plaid: 'bg-sky-100 text-sky-700 dark:bg-sky-950/40 dark:text-sky-400',
    manual: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
  } as Record<string, string>)[source] || 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
}

const emptyAccountForm = () => ({
  id: '',
  name: '',
  institution: '',
  account_type: 'cash',
  display_group: 'Cash',
  include_in_nw: true,
  notes: '',
})

const accountForm = ref(emptyAccountForm())
const editAccountForm = ref(emptyAccountForm())

async function loadAccounts() {
  accountsLoading.value = true
  try {
    accounts.value = await api.getAccounts()
  } catch { /* ignore */ }
  accountsLoading.value = false
}

function startEditAccount(acct: AccountWithBalance) {
  editingAccountId.value = acct.id
  editAccountForm.value = {
    id: acct.id,
    name: acct.name,
    institution: acct.institution || '',
    account_type: acct.account_type,
    display_group: acct.display_group,
    include_in_nw: acct.include_in_nw,
    notes: acct.notes || '',
  }
}

function cancelEditAccount() {
  editingAccountId.value = null
}

async function saveEditAccount() {
  if (!editingAccountId.value) return
  try {
    await api.updateAccount(editingAccountId.value, {
      name: editAccountForm.value.name,
      institution: editAccountForm.value.institution || null,
      account_type: editAccountForm.value.account_type,
      display_group: editAccountForm.value.display_group,
      include_in_nw: editAccountForm.value.include_in_nw,
      notes: editAccountForm.value.notes || null,
    })
    editingAccountId.value = null
    await loadAccounts()
  } catch (e) {
    alert('Failed to update account: ' + (e instanceof Error ? e.message : e))
  }
}

async function saveNewAccount() {
  try {
    const data: Record<string, unknown> = {
      name: accountForm.value.name,
      institution: accountForm.value.institution || null,
      account_type: accountForm.value.account_type,
      display_group: accountForm.value.display_group,
      include_in_nw: accountForm.value.include_in_nw,
      notes: accountForm.value.notes || null,
    }
    if (accountForm.value.id) data.id = accountForm.value.id
    await api.createAccount(data)
    showNewAccountForm.value = false
    accountForm.value = emptyAccountForm()
    await loadAccounts()
  } catch (e) {
    alert('Failed to create account: ' + (e instanceof Error ? e.message : e))
  }
}

// ── Delete account confirmation ──
const deleteTarget = ref<AccountWithBalance | null>(null)
const deleteRelatedCounts = ref<Record<string, number> | null>(null)
const deleteCascade = ref(false)
const deleteBusy = ref(false)
const deleteError = ref<string | null>(null)

const relatedCountLabels: Record<string, string> = {
  balance_snapshots: 'Balance snapshots',
  transactions: 'Transactions',
  mortgages: 'Mortgage records',
  property_valuations: 'Property valuations',
  property_value_history: 'Property value history',
}

async function startDeleteAccount(acct: AccountWithBalance) {
  deleteTarget.value = acct
  deleteRelatedCounts.value = null
  deleteCascade.value = false
  deleteError.value = null
  try {
    deleteRelatedCounts.value = await api.getAccountRelatedCounts(acct.id)
  } catch (e) {
    deleteError.value = 'Failed to load related record counts: ' + (e instanceof Error ? e.message : e)
  }
}

function cancelDeleteAccount() {
  deleteTarget.value = null
  deleteRelatedCounts.value = null
  deleteCascade.value = false
  deleteError.value = null
  deleteBusy.value = false
}

const hasRelatedRecords = () =>
  !!deleteRelatedCounts.value && Object.values(deleteRelatedCounts.value).some((n) => n > 0)

async function confirmDeleteAccount() {
  if (!deleteTarget.value) return
  if (hasRelatedRecords() && !deleteCascade.value) {
    deleteError.value = 'Tick the box to confirm deleting related records, or cancel.'
    return
  }
  deleteBusy.value = true
  deleteError.value = null
  try {
    await api.deleteAccount(deleteTarget.value.id, deleteCascade.value)
    cancelDeleteAccount()
    await loadAccounts()
  } catch (e) {
    deleteError.value = 'Failed to delete account: ' + (e instanceof Error ? e.message : e)
    deleteBusy.value = false
  }
}

// ── Income (W2) ──
const w2Records = ref<W2Record[]>([])
const incomeLoading = ref(false)
const editingW2Year = ref<number | null>(null)
const showNewW2Form = ref(false)

const emptyW2Form = () => ({
  tax_year: new Date().getFullYear(),
  gross_pay: null as number | null,
  base_salary: null as number | null,
  rsu_income: null as number | null,
  federal_tax: null as number | null,
  state_tax: null as number | null,
  pretax_401k: null as number | null,
  roth_401k: null as number | null,
})

const w2Form = ref(emptyW2Form())
const editW2Form = ref(emptyW2Form())

async function loadIncome() {
  incomeLoading.value = true
  try {
    const data = await api.getIncomeHistory()
    w2Records.value = data.w2_records
  } catch { /* ignore */ }
  incomeLoading.value = false
}

function startEditW2(w2: W2Record) {
  editingW2Year.value = w2.tax_year
  editW2Form.value = {
    tax_year: w2.tax_year,
    gross_pay: w2.gross_pay,
    base_salary: w2.base_salary,
    rsu_income: w2.rsu_income,
    federal_tax: w2.federal_tax,
    state_tax: w2.state_tax,
    pretax_401k: w2.pretax_401k,
    roth_401k: w2.roth_401k,
  }
}

function cancelEditW2() {
  editingW2Year.value = null
}

async function saveEditW2() {
  try {
    await api.createW2(editW2Form.value as Record<string, unknown>)
    editingW2Year.value = null
    await loadIncome()
  } catch (e) {
    alert('Failed to update W2: ' + (e instanceof Error ? e.message : e))
  }
}

async function saveNewW2() {
  try {
    await api.createW2(w2Form.value as Record<string, unknown>)
    showNewW2Form.value = false
    w2Form.value = emptyW2Form()
    await loadIncome()
  } catch (e) {
    alert('Failed to create W2: ' + (e instanceof Error ? e.message : e))
  }
}

// ── Import Log ──
const importLogs = ref<any[]>([])
const importLoading = ref(false)

async function loadImportLog() {
  importLoading.value = true
  try {
    importLogs.value = await api.getImportLog()
  } catch { /* ignore */ }
  importLoading.value = false
}

// ── Plaid ──
const API = import.meta.env.VITE_API_URL || ''
const plaidLinks = ref<any[]>([])
const plaidLoading = ref(false)
const plaidStatus = ref('')
const plaidSyncing = ref(false)

async function loadPlaidLinks() {
  plaidLoading.value = true
  try {
    const res = await fetch(`${API}/api/v1/plaid/links`, { credentials: 'include' })
    plaidLinks.value = await res.json()
  } catch { /* ignore */ }
  plaidLoading.value = false
}

async function connectPlaid() {
  plaidStatus.value = 'Getting link token...'
  try {
    const res = await fetch(`${API}/api/v1/plaid/link-token`, { credentials: 'include' })
    const { link_token } = await res.json()
    sessionStorage.setItem('plaid_link_token', link_token)

    const handler = (window as any).Plaid.create({
      token: link_token,
      onSuccess: async (public_token: string, metadata: any) => {
        plaidStatus.value = `Connecting ${metadata.institution?.name || 'institution'}...`
        try {
          const exchangeRes = await fetch(`${API}/api/v1/plaid/exchange`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              public_token,
              institution_name: metadata.institution?.name || 'Unknown',
            }),
          })
          if (!exchangeRes.ok) throw new Error('Exchange failed')
          plaidStatus.value = `Connected ${metadata.institution?.name}! Syncing transactions...`
          await syncPlaid()
          await loadPlaidLinks()
        } catch (e: any) {
          plaidStatus.value = `Error: ${e.message}`
        }
      },
      onExit: (err: any) => {
        if (err) plaidStatus.value = `Link exited: ${err.display_message || err.error_code}`
        else plaidStatus.value = ''
      },
    })
    handler.open()
  } catch (e: any) {
    plaidStatus.value = `Error: ${e.message}`
  }
}

async function syncPlaid() {
  plaidSyncing.value = true
  plaidStatus.value = 'Syncing transactions...'
  try {
    const res = await fetch(`${API}/api/v1/plaid/sync`, { method: 'POST', credentials: 'include' })
    const result = await res.json()
    if (!res.ok) throw new Error(result.detail || 'Sync failed')
    plaidStatus.value = `Synced: ${result.total_added} added, ${result.total_modified} modified, ${result.total_removed} removed`
  } catch (e: any) {
    plaidStatus.value = `Sync error: ${e.message}`
  } finally {
    plaidSyncing.value = false
  }
}

// ── Email Forwarding ──
interface ForwardingEmail { id: number; email: string; is_active: boolean; created_at: string | null }
interface EmailReceiptItem { id: number; from_email: string; subject: string; status: string; transaction_id: string | null; parsed_data: any; error_message: string | null; created_at: string | null }

const forwardingEmails = ref<ForwardingEmail[]>([])
const emailReceipts = ref<EmailReceiptItem[]>([])
const newForwardingEmail = ref('')
const emailError = ref('')
const hostParts = window.location.hostname.split('.')
const domain = hostParts.length > 2 ? hostParts.slice(-2).join('.') : window.location.hostname
const receiptsAddress = `receipts@${domain}`

async function loadForwardingEmails() {
  try {
    const res = await fetch(`${API}/api/v1/email-forwarding`, { credentials: 'include' })
    if (res.ok) forwardingEmails.value = await res.json()
  } catch { /* ignore */ }
}

async function addForwardingEmail() {
  emailError.value = ''
  const email = newForwardingEmail.value.trim()
  if (!email) return
  try {
    const res = await fetch(`${API}/api/v1/email-forwarding`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })
    if (!res.ok) {
      const err = await res.json()
      emailError.value = err.detail || 'Failed to add email'
      return
    }
    newForwardingEmail.value = ''
    await loadForwardingEmails()
  } catch (e: any) {
    emailError.value = e.message
  }
}

async function deleteForwardingEmail(id: number) {
  await fetch(`${API}/api/v1/email-forwarding/${id}`, { method: 'DELETE', credentials: 'include' })
  await loadForwardingEmails()
}

async function loadEmailReceipts() {
  try {
    const res = await fetch(`${API}/api/v1/email-import/receipts?limit=20`, { credentials: 'include' })
    if (res.ok) emailReceipts.value = await res.json()
  } catch { /* ignore */ }
}

// ── Monarch ──
interface MonarchStatus { connected: boolean; email?: string; last_synced_at?: string; created_at?: string }
interface MonarchAccountConfig { id: number; monarch_account_id: string; account_name: string; account_type: string; institution: string; sync_balances: boolean; sync_transactions: boolean; local_account_id: string | null }

const monarchStatus = ref<MonarchStatus>({ connected: false })
const monarchAccounts = ref<MonarchAccountConfig[]>([])
const monarchLoading = ref(false)
const monarchEmail = ref('')
const monarchPassword = ref('')
const monarchConnecting = ref(false)
const monarchStatusMsg = ref('')
const monarchSyncing = ref(false)
const monarchMfaRequired = ref(false)
const monarchMfaCode = ref('')
const monarchUseToken = ref(false)
const monarchToken = ref('')

async function loadMonarchStatus() {
  try {
    const res = await fetch(`${API}/api/v1/monarch/status`, { credentials: 'include' })
    if (res.ok) monarchStatus.value = await res.json()
  } catch { /* ignore */ }
}

async function loadMonarchAccounts() {
  monarchLoading.value = true
  try {
    const res = await fetch(`${API}/api/v1/monarch/accounts`, { credentials: 'include' })
    if (res.ok) monarchAccounts.value = await res.json()
  } catch { /* ignore */ }
  monarchLoading.value = false
}

async function connectMonarch() {
  if (!monarchEmail.value) return
  if (!monarchUseToken.value && !monarchPassword.value) return
  if (monarchUseToken.value && !monarchToken.value) return
  monarchConnecting.value = true
  monarchStatusMsg.value = monarchMfaRequired.value ? 'Verifying MFA code...' : 'Connecting to Monarch Money...'
  try {
    const payload: Record<string, string> = { email: monarchEmail.value }
    if (monarchUseToken.value) {
      payload.token = monarchToken.value
    } else {
      payload.password = monarchPassword.value
      if (monarchMfaRequired.value && monarchMfaCode.value) {
        payload.mfa_code = monarchMfaCode.value
      }
    }
    const res = await fetch(`${API}/api/v1/monarch/connect`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const err = await res.text()
      if (res.status === 429) {
        monarchStatusMsg.value = 'Rate limited by Monarch. Use the session token method instead, or wait and try again later.'
        monarchUseToken.value = true
      } else {
        monarchStatusMsg.value = `Error: ${err}`
      }
      return
    }
    const data = await res.json()
    if (data.mfa_required) {
      monarchMfaRequired.value = true
      monarchStatusMsg.value = 'MFA required — enter the code from your authenticator app.'
      return
    }
    monarchStatusMsg.value = `Connected! Found ${data.accounts_found} accounts.`
    monarchPassword.value = ''
    monarchMfaCode.value = ''
    monarchMfaRequired.value = false
    await loadMonarchStatus()
    await loadMonarchAccounts()
  } catch (e: any) {
    monarchStatusMsg.value = `Error: ${e.message}`
  } finally {
    monarchConnecting.value = false
  }
}

// ── Refresh credentials (token expired but want to keep account configs) ──
const monarchRefreshing = ref(false)
const monarchShowRefresh = ref(false)
const monarchRefreshEmail = ref('')
const monarchRefreshPassword = ref('')
const monarchRefreshToken = ref('')
const monarchRefreshUseToken = ref(false)
const monarchRefreshMfaRequired = ref(false)
const monarchRefreshMfaCode = ref('')

function openRefreshForm() {
  monarchShowRefresh.value = true
  monarchRefreshEmail.value = monarchStatus.value.email || ''
  monarchRefreshPassword.value = ''
  monarchRefreshToken.value = ''
  monarchRefreshUseToken.value = false
  monarchRefreshMfaRequired.value = false
  monarchRefreshMfaCode.value = ''
  monarchStatusMsg.value = ''
}

function cancelRefreshForm() {
  monarchShowRefresh.value = false
  monarchRefreshPassword.value = ''
  monarchRefreshToken.value = ''
  monarchRefreshMfaRequired.value = false
  monarchRefreshMfaCode.value = ''
}

async function refreshMonarchCredentials() {
  if (!monarchRefreshEmail.value) return
  if (!monarchRefreshUseToken.value && !monarchRefreshPassword.value) return
  if (monarchRefreshUseToken.value && !monarchRefreshToken.value) return
  monarchRefreshing.value = true
  monarchStatusMsg.value = monarchRefreshMfaRequired.value
    ? 'Verifying MFA code...'
    : 'Refreshing Monarch credentials...'
  try {
    const payload: Record<string, string> = { email: monarchRefreshEmail.value }
    if (monarchRefreshUseToken.value) {
      payload.token = monarchRefreshToken.value
    } else {
      payload.password = monarchRefreshPassword.value
      if (monarchRefreshMfaRequired.value && monarchRefreshMfaCode.value) {
        payload.mfa_code = monarchRefreshMfaCode.value
      }
    }
    const res = await fetch(`${API}/api/v1/monarch/refresh-credentials`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }))
      monarchStatusMsg.value = `Error: ${body.detail || res.statusText}`
      return
    }
    const data = await res.json()
    if (data.mfa_required) {
      monarchRefreshMfaRequired.value = true
      monarchStatusMsg.value = 'MFA required — enter the code from your authenticator app.'
      return
    }
    monarchStatusMsg.value = 'Credentials refreshed. Account settings preserved.'
    cancelRefreshForm()
    await loadMonarchStatus()
  } catch (e: any) {
    monarchStatusMsg.value = `Error: ${e.message}`
  } finally {
    monarchRefreshing.value = false
  }
}

async function toggleMonarchSync(configId: number, field: 'sync_balances' | 'sync_transactions', value: boolean) {
  try {
    await fetch(`${API}/api/v1/monarch/accounts/${configId}`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [field]: value }),
    })
  } catch { /* ignore */ }
}

async function _safeJson(res: Response): Promise<any> {
  // The backend can return an HTML error page (e.g. nginx 502) before our
  // app ever runs. response.json() on HTML throws an unhelpful syntax error,
  // so handle that explicitly.
  const ct = res.headers.get('content-type') || ''
  if (!ct.includes('application/json')) {
    const body = await res.text()
    throw new Error(`HTTP ${res.status}: ${body.slice(0, 200)}`)
  }
  return res.json()
}

async function syncMonarch() {
  monarchSyncing.value = true
  monarchStatusMsg.value = 'Syncing balances...'
  try {
    const balRes = await fetch(`${API}/api/v1/monarch/sync-balances`, { method: 'POST', credentials: 'include' })
    if (!balRes.ok) {
      const body = await _safeJson(balRes).catch(() => ({ detail: balRes.statusText }))
      throw new Error(body.detail || `HTTP ${balRes.status}`)
    }
    const balData = await _safeJson(balRes)
    monarchStatusMsg.value = `Synced ${balData.synced} account balances. Queuing transaction sync...`

    // POST /sync now returns 202 immediately with a job_id; the actual sync
    // runs in a background task. Poll /sync/status until it reaches a
    // terminal state.
    const enqueueRes = await fetch(`${API}/api/v1/monarch/sync`, { method: 'POST', credentials: 'include' })
    if (!enqueueRes.ok && enqueueRes.status !== 202) {
      const body = await _safeJson(enqueueRes).catch(() => ({ detail: enqueueRes.statusText }))
      throw new Error(body.detail || `HTTP ${enqueueRes.status}`)
    }
    monarchStatusMsg.value = 'Syncing transactions... this can take a few minutes.'

    const POLL_INTERVAL_MS = 2000
    const MAX_POLL_MS = 10 * 60 * 1000  // 10 min hard ceiling
    const started = Date.now()
    let last: any = null
    while (Date.now() - started < MAX_POLL_MS) {
      await new Promise(r => setTimeout(r, POLL_INTERVAL_MS))
      const sRes = await fetch(`${API}/api/v1/monarch/sync/status`, { credentials: 'include' })
      if (!sRes.ok) continue
      last = await _safeJson(sRes).catch(() => null)
      if (!last) continue
      if (last.status !== 'running') break
    }

    if (!last || last.status === 'running') {
      monarchStatusMsg.value = 'Sync still running in background — refresh later to see results.'
    } else if (last.status === 'failed') {
      monarchStatusMsg.value = `Sync failed: ${last.error || 'unknown error'}`
    } else {
      monarchStatusMsg.value = `Done! Balances: ${balData.synced} synced. Transactions: ${last.txn_added} added, ${last.txn_updated} updated.`
    }
    await loadMonarchStatus()
  } catch (e: any) {
    monarchStatusMsg.value = `Sync error: ${e.message}`
  } finally {
    monarchSyncing.value = false
  }
}

async function disconnectMonarch() {
  try {
    await fetch(`${API}/api/v1/monarch/disconnect`, { method: 'DELETE', credentials: 'include' })
    monarchStatus.value = { connected: false }
    monarchAccounts.value = []
    monarchStatusMsg.value = ''
  } catch { /* ignore */ }
}

// ── SimpleFIN ──
interface SimpleFinStatus { connected: boolean; last_synced_at?: string; created_at?: string }
interface SimpleFinAccountConfig { id: number; simplefin_account_id: string; account_name: string; account_type: string | null; institution: string | null; sync_balances: boolean; sync_transactions: boolean; local_account_id: string | null }

const sfStatus = ref<SimpleFinStatus>({ connected: false })
const sfAccounts = ref<SimpleFinAccountConfig[]>([])
const sfLoading = ref(false)
const sfSetupToken = ref('')
const sfConnecting = ref(false)
const sfStatusMsg = ref('')
const sfSyncing = ref(false)

const sfShowRefresh = ref(false)
const sfRefreshToken = ref('')
const sfRefreshing = ref(false)

async function loadSimpleFinStatus() {
  try {
    const res = await fetch(`${API}/api/v1/simplefin/status`, { credentials: 'include' })
    if (res.ok) sfStatus.value = await res.json()
  } catch { /* ignore */ }
}

async function loadSimpleFinAccounts() {
  sfLoading.value = true
  try {
    const res = await fetch(`${API}/api/v1/simplefin/accounts`, { credentials: 'include' })
    if (res.ok) sfAccounts.value = await res.json()
  } catch { /* ignore */ }
  sfLoading.value = false
}

async function connectSimpleFin() {
  if (!sfSetupToken.value.trim()) return
  sfConnecting.value = true
  sfStatusMsg.value = 'Claiming setup token...'
  try {
    const res = await fetch(`${API}/api/v1/simplefin/connect`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ setup_token: sfSetupToken.value.trim() }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }))
      sfStatusMsg.value = `Error: ${body.detail || res.statusText}`
      return
    }
    const data = await res.json()
    sfStatusMsg.value = `Connected — found ${data.accounts_found} accounts.`
    sfSetupToken.value = ''
    await loadSimpleFinStatus()
    await loadSimpleFinAccounts()
  } catch (e: any) {
    sfStatusMsg.value = `Error: ${e.message}`
  } finally {
    sfConnecting.value = false
  }
}

async function toggleSimpleFinSync(configId: number, field: 'sync_balances' | 'sync_transactions', value: boolean) {
  try {
    await fetch(`${API}/api/v1/simplefin/accounts/${configId}`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [field]: value }),
    })
  } catch { /* ignore */ }
}

async function syncSimpleFin() {
  sfSyncing.value = true
  sfStatusMsg.value = 'Queuing SimpleFIN sync...'
  try {
    const enq = await fetch(`${API}/api/v1/simplefin/sync`, { method: 'POST', credentials: 'include' })
    if (!enq.ok && enq.status !== 202) {
      const body = await enq.json().catch(() => ({ detail: enq.statusText }))
      sfStatusMsg.value = `Error: ${body.detail || enq.statusText}`
      return
    }
    sfStatusMsg.value = 'Syncing... fetching accounts and recent transactions.'
    const POLL = 2000, CEILING = 10 * 60 * 1000
    const started = Date.now()
    let last: any = null
    while (Date.now() - started < CEILING) {
      await new Promise(r => setTimeout(r, POLL))
      const sRes = await fetch(`${API}/api/v1/simplefin/sync/status`, { credentials: 'include' })
      if (!sRes.ok) continue
      last = await sRes.json().catch(() => null)
      if (!last) continue
      if (last.status !== 'running') break
    }
    if (!last || last.status === 'running') {
      sfStatusMsg.value = 'Sync still running in background — refresh later for results.'
    } else if (last.status === 'failed') {
      sfStatusMsg.value = `Sync failed: ${last.error || 'unknown error'}`
    } else {
      sfStatusMsg.value = `Done — ${last.balances_synced} balances, ${last.txn_added} added, ${last.txn_updated} updated.`
    }
    await loadSimpleFinStatus()
  } catch (e: any) {
    sfStatusMsg.value = `Sync error: ${e.message}`
  } finally {
    sfSyncing.value = false
  }
}

function openSfRefresh() {
  sfShowRefresh.value = true
  sfRefreshToken.value = ''
  sfStatusMsg.value = ''
}

function cancelSfRefresh() {
  sfShowRefresh.value = false
  sfRefreshToken.value = ''
}

async function refreshSimpleFinCredentials() {
  if (!sfRefreshToken.value.trim()) return
  sfRefreshing.value = true
  sfStatusMsg.value = 'Refreshing SimpleFIN credentials...'
  try {
    const res = await fetch(`${API}/api/v1/simplefin/refresh-credentials`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ setup_token: sfRefreshToken.value.trim() }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }))
      sfStatusMsg.value = `Error: ${body.detail || res.statusText}`
      return
    }
    sfStatusMsg.value = 'Credentials refreshed. Account settings preserved.'
    cancelSfRefresh()
    await loadSimpleFinStatus()
  } catch (e: any) {
    sfStatusMsg.value = `Error: ${e.message}`
  } finally {
    sfRefreshing.value = false
  }
}

async function disconnectSimpleFin() {
  try {
    await fetch(`${API}/api/v1/simplefin/disconnect`, { method: 'DELETE', credentials: 'include' })
    sfStatus.value = { connected: false }
    sfAccounts.value = []
    sfStatusMsg.value = ''
  } catch { /* ignore */ }
}

// Load data on mount
onMounted(() => {
  loadAccounts()
  loadIncome()
  loadPlaidLinks()
  // Monarch tab hidden — skip its loaders. Re-add when the tab is re-enabled.
  loadSimpleFinStatus()
  loadSimpleFinAccounts()
  loadImportLog()
  loadForwardingEmails()
  loadEmailReceipts()
})
</script>

<template>
  <div>
    <h2 class="text-lg font-bold text-gray-900 dark:text-white mb-6">Settings</h2>

    <!-- Tabs -->
    <div class="flex gap-2 mb-6">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        @click="activeTab = tab.key"
        :class="[
          'px-4 py-2 text-sm rounded-lg transition-colors font-medium',
          activeTab === tab.key
            ? 'bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300'
            : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
        ]"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- ═══ Accounts Tab ═══ -->
    <div v-if="activeTab === 'accounts'" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
      <div class="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-800">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Accounts</h3>
        <button
          @click="showNewAccountForm = !showNewAccountForm"
          class="px-3 py-1.5 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium"
        >
          {{ showNewAccountForm ? 'Cancel' : 'Add Account' }}
        </button>
      </div>

      <!-- New Account Form -->
      <div v-if="showNewAccountForm" class="px-5 py-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">ID (optional)</label>
            <input v-model="accountForm.id" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" placeholder="Auto-generated" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Name</label>
            <input v-model="accountForm.name" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Institution</label>
            <input v-model="accountForm.institution" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Type</label>
            <select v-model="accountForm.account_type" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white">
              <option v-for="t in accountTypes" :key="t" :value="t">{{ t }}</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Display Group</label>
            <select v-model="accountForm.display_group" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white">
              <option v-for="g in displayGroups" :key="g" :value="g">{{ g }}</option>
            </select>
          </div>
          <div class="flex items-end">
            <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
              <input type="checkbox" v-model="accountForm.include_in_nw" class="rounded" />
              Include in Net Worth
            </label>
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Notes</label>
            <input v-model="accountForm.notes" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
          </div>
          <div class="flex items-end gap-2">
            <button @click="saveNewAccount" class="px-3 py-1.5 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium">Save</button>
            <button @click="showNewAccountForm = false; accountForm = emptyAccountForm()" class="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">Cancel</button>
          </div>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="accountsLoading" class="flex items-center justify-center h-32">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
      </div>

      <!-- Table -->
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-100 dark:border-gray-800">
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Name</th>
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Institution</th>
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Type</th>
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Group</th>
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Source</th>
              <th class="text-center px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Active</th>
              <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Balance</th>
              <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="acct in accounts" :key="acct.id">
              <!-- Display Row -->
              <tr v-if="editingAccountId !== acct.id" class="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                <td class="px-5 py-3 text-gray-900 dark:text-white">{{ acct.name }}</td>
                <td class="px-5 py-3 text-gray-600 dark:text-gray-400">{{ acct.institution || '\u2014' }}</td>
                <td class="px-5 py-3 text-gray-600 dark:text-gray-400">{{ acct.account_type }}</td>
                <td class="px-5 py-3 text-gray-600 dark:text-gray-400">{{ acct.display_group }}</td>
                <td class="px-5 py-3">
                  <span class="inline-block px-2 py-0.5 text-xs rounded font-medium" :class="sourceBadgeClass(acct.source)">
                    {{ sourceLabel(acct.source) }}
                  </span>
                </td>
                <td class="px-5 py-3 text-center">
                  <span :class="acct.is_active ? 'text-green-600 dark:text-green-400' : 'text-gray-400'">
                    {{ acct.is_active ? 'Yes' : 'No' }}
                  </span>
                </td>
                <td class="px-5 py-3 text-right font-medium text-gray-900 dark:text-white">
                  {{ acct.current_balance != null ? currency(acct.current_balance) : '\u2014' }}
                </td>
                <td class="px-5 py-3 text-right">
                  <div class="flex gap-3 justify-end">
                    <button @click="startEditAccount(acct)" class="text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 text-sm font-medium">
                      Edit
                    </button>
                    <button @click="startDeleteAccount(acct)" class="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 text-sm font-medium">
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
              <!-- Edit Row -->
              <tr v-else class="border-b border-gray-50 dark:border-gray-800 bg-indigo-50/50 dark:bg-indigo-950/30">
                <td class="px-5 py-2">
                  <input v-model="editAccountForm.name" class="w-full px-2 py-1 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
                </td>
                <td class="px-5 py-2">
                  <input v-model="editAccountForm.institution" class="w-full px-2 py-1 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
                </td>
                <td class="px-5 py-2">
                  <select v-model="editAccountForm.account_type" class="w-full px-2 py-1 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white">
                    <option v-for="t in accountTypes" :key="t" :value="t">{{ t }}</option>
                  </select>
                </td>
                <td class="px-5 py-2">
                  <select v-model="editAccountForm.display_group" class="w-full px-2 py-1 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white">
                    <option v-for="g in displayGroups" :key="g" :value="g">{{ g }}</option>
                  </select>
                </td>
                <td class="px-5 py-2 text-gray-400 text-xs">\u2014</td>
                <td class="px-5 py-2 text-center">
                  <input type="checkbox" v-model="editAccountForm.include_in_nw" class="rounded" />
                </td>
                <td class="px-5 py-2 text-right text-gray-400 text-sm">\u2014</td>
                <td class="px-5 py-2 text-right">
                  <div class="flex gap-1 justify-end">
                    <button @click="saveEditAccount" class="px-2 py-1 text-xs rounded bg-indigo-600 text-white hover:bg-indigo-700 transition-colors">Save</button>
                    <button @click="cancelEditAccount" class="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">Cancel</button>
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="accounts.length === 0 && !accountsLoading">
              <td colspan="8" class="px-5 py-8 text-center text-gray-500 dark:text-gray-400">
                No accounts found
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Delete Account Modal -->
    <div v-if="deleteTarget" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4" @click.self="cancelDeleteAccount">
      <div class="w-full max-w-md bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-xl">
        <div class="px-5 py-4 border-b border-gray-200 dark:border-gray-800">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Delete account</h3>
        </div>
        <div class="px-5 py-4 space-y-4">
          <p class="text-sm text-gray-700 dark:text-gray-300">
            Delete <span class="font-medium text-gray-900 dark:text-white">{{ deleteTarget.name }}</span>?
          </p>

          <div v-if="deleteRelatedCounts === null && !deleteError" class="text-sm text-gray-500 dark:text-gray-400">
            Loading related records...
          </div>

          <div v-else-if="deleteRelatedCounts && hasRelatedRecords()" class="space-y-3">
            <div class="text-xs text-gray-500 dark:text-gray-400">
              This account has related records:
            </div>
            <ul class="text-sm text-gray-700 dark:text-gray-300 space-y-1 pl-4">
              <li v-for="(count, key) in deleteRelatedCounts" :key="key" v-show="count > 0">
                <span class="font-medium">{{ count.toLocaleString() }}</span>
                {{ relatedCountLabels[key] || key }}
              </li>
            </ul>
            <label class="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
              <input type="checkbox" v-model="deleteCascade" class="mt-0.5 rounded" />
              <span>Also delete all related records listed above. This cannot be undone.</span>
            </label>
          </div>

          <div v-else-if="deleteRelatedCounts" class="text-sm text-gray-600 dark:text-gray-400">
            No related records — only the account row will be removed.
          </div>

          <div v-if="deleteError" class="text-sm text-red-600 dark:text-red-400">
            {{ deleteError }}
          </div>
        </div>
        <div class="px-5 py-3 border-t border-gray-200 dark:border-gray-800 flex justify-end gap-2">
          <button
            @click="cancelDeleteAccount"
            :disabled="deleteBusy"
            class="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            @click="confirmDeleteAccount"
            :disabled="deleteBusy || deleteRelatedCounts === null || (hasRelatedRecords() && !deleteCascade)"
            class="px-3 py-1.5 text-sm rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 disabled:hover:bg-red-600"
          >
            {{ deleteBusy ? 'Deleting...' : 'Delete' }}
          </button>
        </div>
      </div>
    </div>

    <!-- ═══ Income Tab ═══ -->
    <div v-if="activeTab === 'income'" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
      <div class="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-800">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">W2 Records</h3>
        <button
          @click="showNewW2Form = !showNewW2Form"
          class="px-3 py-1.5 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium"
        >
          {{ showNewW2Form ? 'Cancel' : 'Add W2' }}
        </button>
      </div>

      <!-- New W2 Form -->
      <div v-if="showNewW2Form" class="px-5 py-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Tax Year</label>
            <input v-model.number="w2Form.tax_year" type="number" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Gross Pay</label>
            <input v-model.number="w2Form.gross_pay" type="number" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Base Salary</label>
            <input v-model.number="w2Form.base_salary" type="number" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">RSU Income</label>
            <input v-model.number="w2Form.rsu_income" type="number" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Federal Tax</label>
            <input v-model.number="w2Form.federal_tax" type="number" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">State Tax</label>
            <input v-model.number="w2Form.state_tax" type="number" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Pre-tax 401k</label>
            <input v-model.number="w2Form.pretax_401k" type="number" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Roth 401k</label>
            <input v-model.number="w2Form.roth_401k" type="number" class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
          </div>
        </div>
        <div class="mt-3 flex gap-2">
          <button @click="saveNewW2" class="px-3 py-1.5 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium">Save</button>
          <button @click="showNewW2Form = false; w2Form = emptyW2Form()" class="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">Cancel</button>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="incomeLoading" class="flex items-center justify-center h-32">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
      </div>

      <!-- Table -->
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-100 dark:border-gray-800">
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Tax Year</th>
              <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Gross Pay</th>
              <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Base Salary</th>
              <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">RSU Income</th>
              <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Federal Tax</th>
              <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">State Tax</th>
              <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Pre-tax 401k</th>
              <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Roth 401k</th>
              <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="w2 in w2Records" :key="w2.tax_year">
              <!-- Display Row -->
              <tr v-if="editingW2Year !== w2.tax_year" class="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                <td class="px-5 py-3 text-gray-900 dark:text-white font-medium">{{ w2.tax_year }}</td>
                <td class="px-5 py-3 text-right text-gray-900 dark:text-white">{{ w2.gross_pay != null ? currency(w2.gross_pay) : '\u2014' }}</td>
                <td class="px-5 py-3 text-right text-gray-600 dark:text-gray-400">{{ w2.base_salary != null ? currency(w2.base_salary) : '\u2014' }}</td>
                <td class="px-5 py-3 text-right text-gray-600 dark:text-gray-400">{{ w2.rsu_income != null ? currency(w2.rsu_income) : '\u2014' }}</td>
                <td class="px-5 py-3 text-right text-red-600 dark:text-red-400">{{ w2.federal_tax != null ? currency(w2.federal_tax) : '\u2014' }}</td>
                <td class="px-5 py-3 text-right text-red-600 dark:text-red-400">{{ w2.state_tax != null ? currency(w2.state_tax) : '\u2014' }}</td>
                <td class="px-5 py-3 text-right text-gray-600 dark:text-gray-400">{{ w2.pretax_401k != null ? currency(w2.pretax_401k) : '\u2014' }}</td>
                <td class="px-5 py-3 text-right text-gray-600 dark:text-gray-400">{{ w2.roth_401k != null ? currency(w2.roth_401k) : '\u2014' }}</td>
                <td class="px-5 py-3 text-right">
                  <button @click="startEditW2(w2)" class="text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 text-sm font-medium">Edit</button>
                </td>
              </tr>
              <!-- Edit Row -->
              <tr v-else class="border-b border-gray-50 dark:border-gray-800 bg-indigo-50/50 dark:bg-indigo-950/30">
                <td class="px-5 py-2 text-gray-900 dark:text-white font-medium">{{ editW2Form.tax_year }}</td>
                <td class="px-5 py-2"><input v-model.number="editW2Form.gross_pay" type="number" class="w-full px-2 py-1 text-sm text-right rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" /></td>
                <td class="px-5 py-2"><input v-model.number="editW2Form.base_salary" type="number" class="w-full px-2 py-1 text-sm text-right rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" /></td>
                <td class="px-5 py-2"><input v-model.number="editW2Form.rsu_income" type="number" class="w-full px-2 py-1 text-sm text-right rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" /></td>
                <td class="px-5 py-2"><input v-model.number="editW2Form.federal_tax" type="number" class="w-full px-2 py-1 text-sm text-right rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" /></td>
                <td class="px-5 py-2"><input v-model.number="editW2Form.state_tax" type="number" class="w-full px-2 py-1 text-sm text-right rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" /></td>
                <td class="px-5 py-2"><input v-model.number="editW2Form.pretax_401k" type="number" class="w-full px-2 py-1 text-sm text-right rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" /></td>
                <td class="px-5 py-2"><input v-model.number="editW2Form.roth_401k" type="number" class="w-full px-2 py-1 text-sm text-right rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" /></td>
                <td class="px-5 py-2 text-right">
                  <div class="flex gap-1 justify-end">
                    <button @click="saveEditW2" class="px-2 py-1 text-xs rounded bg-indigo-600 text-white hover:bg-indigo-700 transition-colors">Save</button>
                    <button @click="cancelEditW2" class="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">Cancel</button>
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="w2Records.length === 0 && !incomeLoading">
              <td colspan="9" class="px-5 py-8 text-center text-gray-500 dark:text-gray-400">
                No W2 records found
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ═══ Plaid Tab ═══ -->
    <div v-if="activeTab === 'plaid'" class="space-y-4">
      <!-- Connect -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
        <div class="flex items-center justify-between mb-3">
          <div>
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Connect Bank Account</h3>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Link your bank, credit card, or brokerage via Plaid for automatic transaction sync</p>
          </div>
          <button @click="connectPlaid"
            class="px-4 py-2 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">
            Connect Account
          </button>
        </div>
        <div v-if="plaidStatus" class="text-xs" :class="plaidStatus.startsWith('Error') || plaidStatus.startsWith('Sync error') ? 'text-red-500' : 'text-green-600 dark:text-green-400'">
          {{ plaidStatus }}
        </div>
      </div>

      <!-- Connected Institutions -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Connected Institutions</h3>
          <button v-if="plaidLinks.length > 0" @click="syncPlaid" :disabled="plaidSyncing"
            class="px-3 py-1.5 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50">
            {{ plaidSyncing ? 'Syncing...' : 'Sync All' }}
          </button>
        </div>
        <div v-if="plaidLoading" class="px-5 py-8 text-center text-sm text-gray-400">Loading...</div>
        <div v-else-if="plaidLinks.length === 0" class="px-5 py-8 text-center text-sm text-gray-400">
          No accounts connected yet. Click "Connect Account" to get started.
        </div>
        <table v-else class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-100 dark:border-gray-800 text-gray-500 dark:text-gray-400">
              <th class="text-left px-5 py-2.5 font-medium">Institution</th>
              <th class="text-left px-3 py-2.5 font-medium">Connected</th>
              <th class="text-left px-3 py-2.5 font-medium">Last Synced</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="link in plaidLinks" :key="link.id"
              class="border-b border-gray-50 dark:border-gray-800 last:border-0">
              <td class="px-5 py-2.5 font-medium text-gray-900 dark:text-white">{{ link.institution_name || 'Unknown' }}</td>
              <td class="px-3 py-2.5 text-gray-500 dark:text-gray-400">{{ new Date(link.created_at).toLocaleDateString() }}</td>
              <td class="px-3 py-2.5 text-gray-500 dark:text-gray-400">{{ link.cursor ? 'Yes' : 'Never' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ═══ Monarch Tab ═══ -->
    <div v-if="activeTab === 'monarch'" class="space-y-4">
      <!-- Not connected: login form -->
      <div v-if="!monarchStatus.connected" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">Connect Monarch Money</h3>
        <p class="text-xs text-gray-400 dark:text-gray-500 mb-4">Enter your Monarch Money credentials to sync account balances and transactions.</p>
        <div class="max-w-sm space-y-3">
          <input v-model="monarchEmail" type="email" placeholder="Email" :disabled="monarchMfaRequired"
            class="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 disabled:opacity-50" />

          <!-- Token auth mode -->
          <template v-if="monarchUseToken">
            <div class="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg p-3">
              <p class="text-xs text-amber-700 dark:text-amber-400 leading-relaxed">
                To get your session token: log into <a href="https://app.monarchmoney.com" target="_blank" class="underline font-medium">app.monarchmoney.com</a>,
                open DevTools (F12) &rarr; Network tab &rarr; find any request to <code class="font-mono bg-amber-100 dark:bg-amber-900 px-1 rounded">api.monarchmoney.com</code>
                &rarr; look at the request headers &rarr; copy the value after <code class="font-mono bg-amber-100 dark:bg-amber-900 px-1 rounded">Authorization: Token</code>.
              </p>
            </div>
            <input v-model="monarchToken" type="text" placeholder="Session token" autofocus
              class="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 font-mono text-[11px]"
              @keyup.enter="connectMonarch" />
          </template>

          <!-- Password auth mode -->
          <template v-else>
            <input v-model="monarchPassword" type="password" placeholder="Password" :disabled="monarchMfaRequired"
              class="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 disabled:opacity-50"
              @keyup.enter="!monarchMfaRequired && connectMonarch()" />
            <input v-if="monarchMfaRequired" v-model="monarchMfaCode" type="text" inputmode="numeric" placeholder="MFA Code" autofocus
              class="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 font-mono tracking-widest"
              @keyup.enter="connectMonarch" />
          </template>

          <div class="flex items-center gap-2">
            <button @click="connectMonarch"
              :disabled="monarchConnecting || !monarchEmail || (!monarchUseToken && !monarchPassword) || (monarchUseToken && !monarchToken) || (monarchMfaRequired && !monarchUseToken && !monarchMfaCode)"
              class="px-4 py-2 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
              {{ monarchConnecting ? 'Connecting...' : monarchMfaRequired && !monarchUseToken ? 'Verify' : 'Connect' }}
            </button>
            <button v-if="monarchMfaRequired || monarchUseToken"
              @click="monarchMfaRequired = false; monarchMfaCode = ''; monarchUseToken = false; monarchToken = ''; monarchStatusMsg = ''"
              class="px-3 py-2 text-xs font-medium text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
              Cancel
            </button>
            <button v-if="!monarchUseToken && !monarchMfaRequired"
              @click="monarchUseToken = true; monarchStatusMsg = ''"
              class="px-3 py-2 text-xs font-medium text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
              Use session token instead
            </button>
          </div>
        </div>
        <div v-if="monarchStatusMsg" class="mt-3 text-xs" :class="monarchStatusMsg.startsWith('Error') ? 'text-red-500' : 'text-green-600 dark:text-green-400'">
          {{ monarchStatusMsg }}
        </div>
      </div>

      <!-- Connected: status + sync -->
      <template v-else>
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Monarch Money Connected</h3>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                {{ monarchStatus.email }}
                <span v-if="monarchStatus.last_synced_at"> &middot; Last synced: {{ new Date(monarchStatus.last_synced_at).toLocaleString() }}</span>
                <span v-else> &middot; Never synced</span>
              </p>
            </div>
            <div class="flex items-center gap-2">
              <button @click="syncMonarch" :disabled="monarchSyncing"
                class="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                {{ monarchSyncing ? 'Syncing...' : 'Sync All' }}
              </button>
              <button @click="openRefreshForm" :disabled="monarchRefreshing"
                class="px-3 py-1.5 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 rounded-lg transition-colors disabled:opacity-50">
                Refresh credentials
              </button>
              <button @click="disconnectMonarch"
                class="px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-lg transition-colors">
                Disconnect
              </button>
            </div>
          </div>
          <div v-if="monarchStatusMsg" class="mt-3 text-xs" :class="monarchStatusMsg.startsWith('Error') || monarchStatusMsg.startsWith('Sync error') ? 'text-red-500' : 'text-green-600 dark:text-green-400'">
            {{ monarchStatusMsg }}
          </div>

          <!-- Refresh credentials inline form -->
          <div v-if="monarchShowRefresh" class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800 space-y-3">
            <div>
              <h4 class="text-xs font-semibold text-gray-700 dark:text-gray-300">Refresh expired credentials</h4>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Updates the session token without disconnecting accounts. Per-account sync settings are preserved.</p>
            </div>
            <input v-model="monarchRefreshEmail" type="email" placeholder="Email" :disabled="monarchRefreshMfaRequired"
              class="w-full px-3 py-1.5 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white disabled:opacity-50" />
            <template v-if="monarchRefreshUseToken">
              <input v-model="monarchRefreshToken" type="password" placeholder="Session token"
                class="w-full px-3 py-1.5 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                @keyup.enter="refreshMonarchCredentials" />
            </template>
            <template v-else>
              <input v-model="monarchRefreshPassword" type="password" placeholder="Password" :disabled="monarchRefreshMfaRequired"
                class="w-full px-3 py-1.5 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white disabled:opacity-50"
                @keyup.enter="!monarchRefreshMfaRequired && refreshMonarchCredentials()" />
              <input v-if="monarchRefreshMfaRequired" v-model="monarchRefreshMfaCode" type="text" placeholder="MFA code (6 digits)" autofocus
                class="w-full px-3 py-1.5 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white tracking-widest text-center"
                @keyup.enter="refreshMonarchCredentials" />
            </template>
            <div class="flex items-center justify-between">
              <button v-if="!monarchRefreshUseToken && !monarchRefreshMfaRequired"
                @click="monarchRefreshUseToken = true; monarchStatusMsg = ''"
                class="text-xs text-indigo-600 dark:text-indigo-400 hover:underline">
                Use session token instead
              </button>
              <button v-else-if="monarchRefreshUseToken"
                @click="monarchRefreshUseToken = false; monarchRefreshToken = ''; monarchStatusMsg = ''"
                class="text-xs text-indigo-600 dark:text-indigo-400 hover:underline">
                Use password instead
              </button>
              <span v-else></span>
              <div class="flex items-center gap-2">
                <button @click="cancelRefreshForm"
                  class="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                  Cancel
                </button>
                <button @click="refreshMonarchCredentials"
                  :disabled="monarchRefreshing || !monarchRefreshEmail || (!monarchRefreshUseToken && !monarchRefreshPassword) || (monarchRefreshUseToken && !monarchRefreshToken) || (monarchRefreshMfaRequired && !monarchRefreshUseToken && !monarchRefreshMfaCode)"
                  class="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                  {{ monarchRefreshing ? 'Refreshing...' : monarchRefreshMfaRequired && !monarchRefreshUseToken ? 'Verify' : 'Refresh' }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Account Configuration -->
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
          <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-800">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Account Sync Configuration</h3>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Choose which accounts to sync balances and transactions for.</p>
          </div>
          <div v-if="monarchLoading" class="px-5 py-8 text-center text-sm text-gray-400">Loading...</div>
          <div v-else-if="monarchAccounts.length === 0" class="px-5 py-8 text-center text-sm text-gray-400">
            No accounts found. Try syncing again.
          </div>
          <table v-else class="w-full text-sm">
            <thead>
              <tr class="border-b border-gray-100 dark:border-gray-800 text-gray-500 dark:text-gray-400">
                <th class="text-left px-5 py-2.5 font-medium">Account</th>
                <th class="text-left px-3 py-2.5 font-medium">Institution</th>
                <th class="text-left px-3 py-2.5 font-medium">Type</th>
                <th class="text-center px-3 py-2.5 font-medium">Balances</th>
                <th class="text-center px-3 py-2.5 font-medium">Transactions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="acct in monarchAccounts" :key="acct.id"
                class="border-b border-gray-50 dark:border-gray-800 last:border-0">
                <td class="px-5 py-2.5 font-medium text-gray-900 dark:text-white">{{ acct.account_name }}</td>
                <td class="px-3 py-2.5 text-gray-500 dark:text-gray-400">{{ acct.institution || '—' }}</td>
                <td class="px-3 py-2.5 text-gray-500 dark:text-gray-400">{{ acct.account_type || '—' }}</td>
                <td class="px-3 py-2.5 text-center">
                  <input type="checkbox" :checked="acct.sync_balances"
                    @change="acct.sync_balances = !acct.sync_balances; toggleMonarchSync(acct.id, 'sync_balances', acct.sync_balances)"
                    class="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500 dark:bg-gray-800" />
                </td>
                <td class="px-3 py-2.5 text-center">
                  <input type="checkbox" :checked="acct.sync_transactions"
                    @change="acct.sync_transactions = !acct.sync_transactions; toggleMonarchSync(acct.id, 'sync_transactions', acct.sync_transactions)"
                    class="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500 dark:bg-gray-800" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>

    <!-- ═══ SimpleFIN Tab ═══ -->
    <div v-if="activeTab === 'simplefin'" class="space-y-4">
      <div v-if="!sfStatus.connected" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">Connect SimpleFIN Bridge</h3>
        <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">
          Get a setup token from
          <a href="https://beta-bridge.simplefin.org/" target="_blank" class="text-indigo-600 dark:text-indigo-400 hover:underline">beta-bridge.simplefin.org</a>
          and paste it below. Tokens are single-use — once claimed, the access URL is stored.
        </p>
        <div class="space-y-2">
          <textarea v-model="sfSetupToken" placeholder="Paste base64 setup token here"
            rows="3"
            class="w-full px-3 py-2 text-xs font-mono border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"></textarea>
          <div class="flex justify-end">
            <button @click="connectSimpleFin"
              :disabled="sfConnecting || !sfSetupToken.trim()"
              class="px-4 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
              {{ sfConnecting ? 'Connecting...' : 'Connect' }}
            </button>
          </div>
          <div v-if="sfStatusMsg" class="text-xs" :class="sfStatusMsg.startsWith('Error') ? 'text-red-500' : 'text-green-600 dark:text-green-400'">
            {{ sfStatusMsg }}
          </div>
        </div>
      </div>

      <template v-else>
        <!-- Connected status + actions -->
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">SimpleFIN Connected</h3>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                <span v-if="sfStatus.last_synced_at">Last synced: {{ new Date(sfStatus.last_synced_at).toLocaleString() }}</span>
                <span v-else>Never synced</span>
              </p>
            </div>
            <div class="flex items-center gap-2">
              <button @click="syncSimpleFin" :disabled="sfSyncing"
                class="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                {{ sfSyncing ? 'Syncing...' : 'Sync All' }}
              </button>
              <button @click="openSfRefresh" :disabled="sfRefreshing"
                class="px-3 py-1.5 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 rounded-lg disabled:opacity-50">
                Refresh credentials
              </button>
              <button @click="disconnectSimpleFin"
                class="px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-lg">
                Disconnect
              </button>
            </div>
          </div>
          <div v-if="sfStatusMsg" class="mt-3 text-xs" :class="sfStatusMsg.startsWith('Error') || sfStatusMsg.startsWith('Sync error') ? 'text-red-500' : 'text-green-600 dark:text-green-400'">
            {{ sfStatusMsg }}
          </div>

          <!-- Refresh inline form -->
          <div v-if="sfShowRefresh" class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800 space-y-2">
            <h4 class="text-xs font-semibold text-gray-700 dark:text-gray-300">Refresh access URL</h4>
            <p class="text-xs text-gray-400 dark:text-gray-500">Paste a fresh setup token. Account configs are preserved.</p>
            <textarea v-model="sfRefreshToken" placeholder="New setup token"
              rows="3"
              class="w-full px-3 py-2 text-xs font-mono border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"></textarea>
            <div class="flex items-center justify-end gap-2">
              <button @click="cancelSfRefresh"
                class="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                Cancel
              </button>
              <button @click="refreshSimpleFinCredentials"
                :disabled="sfRefreshing || !sfRefreshToken.trim()"
                class="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                {{ sfRefreshing ? 'Refreshing...' : 'Refresh' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Account configuration -->
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
          <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-800">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Account Sync Configuration</h3>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">SimpleFIN returns balances + ~45 days of transactions per account.</p>
          </div>
          <div v-if="sfLoading" class="px-5 py-4 text-xs text-gray-400">Loading...</div>
          <div v-else-if="sfAccounts.length === 0" class="px-5 py-4 text-xs text-gray-400">No accounts.</div>
          <table v-else class="w-full text-xs">
            <thead class="bg-gray-50 dark:bg-gray-950/50 border-b border-gray-100 dark:border-gray-800">
              <tr>
                <th class="text-left px-5 py-2 font-medium text-gray-600 dark:text-gray-400">Account</th>
                <th class="text-left px-3 py-2 font-medium text-gray-600 dark:text-gray-400">Institution</th>
                <th class="text-center px-3 py-2 font-medium text-gray-600 dark:text-gray-400">Balances</th>
                <th class="text-center px-3 py-2 font-medium text-gray-600 dark:text-gray-400">Transactions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
              <tr v-for="cfg in sfAccounts" :key="cfg.id">
                <td class="px-5 py-2 text-gray-900 dark:text-white">{{ cfg.account_name }}</td>
                <td class="px-3 py-2 text-gray-500 dark:text-gray-400">{{ cfg.institution || '—' }}</td>
                <td class="px-3 py-2 text-center">
                  <input type="checkbox" :checked="cfg.sync_balances"
                    @change="(e) => { const v = (e.target as HTMLInputElement).checked; cfg.sync_balances = v; toggleSimpleFinSync(cfg.id, 'sync_balances', v) }"
                    class="rounded text-indigo-600" />
                </td>
                <td class="px-3 py-2 text-center">
                  <input type="checkbox" :checked="cfg.sync_transactions"
                    @change="(e) => { const v = (e.target as HTMLInputElement).checked; cfg.sync_transactions = v; toggleSimpleFinSync(cfg.id, 'sync_transactions', v) }"
                    class="rounded text-indigo-600" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>

    <!-- ═══ Email Tab ═══ -->
    <div v-if="activeTab === 'email'" class="space-y-4">
      <!-- Instructions -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">Email Receipt Import</h3>
        <p class="text-xs text-gray-500 dark:text-gray-400">
          Forward receipts from Amazon, PayPal, or any merchant to <span class="font-mono text-indigo-600 dark:text-indigo-400">{{ receiptsAddress }}</span> and they'll be automatically parsed into transactions.
        </p>
      </div>

      <!-- Registered Emails -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Forwarding Addresses</h3>
        <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">Register the email addresses you'll forward receipts from. Only emails from registered addresses will be processed.</p>

        <!-- Add form -->
        <div class="flex gap-2 mb-3">
          <input v-model="newForwardingEmail" type="email" placeholder="your.email@gmail.com"
            class="flex-1 px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white placeholder-gray-400"
            @keyup.enter="addForwardingEmail" />
          <button @click="addForwardingEmail"
            class="px-4 py-2 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">
            Add
          </button>
        </div>
        <div v-if="emailError" class="text-xs text-red-500 mb-3">{{ emailError }}</div>

        <!-- List -->
        <div v-if="forwardingEmails.length === 0" class="text-xs text-gray-400 py-2">
          No forwarding addresses registered yet.
        </div>
        <div v-else class="space-y-2">
          <div v-for="addr in forwardingEmails" :key="addr.id"
            class="flex items-center justify-between py-2 px-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <span class="text-sm text-gray-900 dark:text-white">{{ addr.email }}</span>
            <button @click="deleteForwardingEmail(addr.id)"
              class="text-xs text-red-500 hover:text-red-700">Remove</button>
          </div>
        </div>
      </div>

      <!-- Recent Receipts -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-800">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Recent Receipts</h3>
        </div>
        <div v-if="emailReceipts.length === 0" class="px-5 py-8 text-center text-sm text-gray-400">
          No email receipts yet. Forward a receipt to get started.
        </div>
        <table v-else class="w-full text-sm">
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
            <tr v-for="r in emailReceipts" :key="r.id" class="border-b border-gray-50 dark:border-gray-800 last:border-0">
              <td class="px-5 py-2.5 text-gray-500 dark:text-gray-400 whitespace-nowrap">{{ r.created_at ? new Date(r.created_at).toLocaleDateString() : '\u2014' }}</td>
              <td class="px-3 py-2.5 text-gray-600 dark:text-gray-400 truncate max-w-[150px]">{{ r.from_email }}</td>
              <td class="px-3 py-2.5 text-gray-900 dark:text-white truncate max-w-[200px]">{{ r.subject }}</td>
              <td class="px-3 py-2.5 text-gray-900 dark:text-white">{{ r.parsed_data?.merchant || '\u2014' }}</td>
              <td class="px-3 py-2.5 text-right text-gray-900 dark:text-white">{{ r.parsed_data?.amount ? currency(r.parsed_data.amount) : '\u2014' }}</td>
              <td class="px-5 py-2.5">
                <span :class="[
                  'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
                  r.status === 'parsed' ? 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300' :
                  r.status === 'failed' ? 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300' :
                  'bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300'
                ]">{{ r.status }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ═══ Import Tab ═══ -->
    <div v-if="activeTab === 'import'" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
      <div class="px-5 py-4 border-b border-gray-200 dark:border-gray-800">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Import History</h3>
      </div>

      <!-- Loading -->
      <div v-if="importLoading" class="flex items-center justify-center h-32">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
      </div>

      <!-- Table -->
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-100 dark:border-gray-800">
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Date</th>
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Source</th>
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Capture Mode</th>
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Status</th>
              <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Records Created</th>
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Error</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="log in importLogs"
              :key="log.id"
              class="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800"
            >
              <td class="px-5 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">
                {{ log.created_at ? new Date(log.created_at).toLocaleDateString() : '\u2014' }}
              </td>
              <td class="px-5 py-3 text-gray-900 dark:text-white">{{ log.source }}</td>
              <td class="px-5 py-3 text-gray-600 dark:text-gray-400">{{ log.capture_mode || '\u2014' }}</td>
              <td class="px-5 py-3">
                <span :class="[
                  'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
                  log.status === 'completed' ? 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300' :
                  log.status === 'error' ? 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300' :
                  'bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300'
                ]">
                  {{ log.status }}
                </span>
              </td>
              <td class="px-5 py-3 text-right text-gray-900 dark:text-white">{{ log.records_created }}</td>
              <td class="px-5 py-3 text-red-600 dark:text-red-400 text-xs max-w-xs truncate">
                {{ log.error_message || '\u2014' }}
              </td>
            </tr>
            <tr v-if="importLogs.length === 0 && !importLoading">
              <td colspan="6" class="px-5 py-8 text-center text-gray-500 dark:text-gray-400">
                No import logs found
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
