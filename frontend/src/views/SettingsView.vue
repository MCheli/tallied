<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../api/client'
import { useFormatters } from '../composables/useFormatters'
import type { AccountWithBalance, W2Record } from '../types'

const { currency } = useFormatters()

// Tab management
type Tab = 'accounts' | 'income' | 'plaid' | 'email' | 'import'
const activeTab = ref<Tab>('accounts')
const tabs: { key: Tab; label: string }[] = [
  { key: 'accounts', label: 'Accounts' },
  { key: 'income', label: 'Income' },
  { key: 'plaid', label: 'Plaid' },
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

// Load data on mount
onMounted(() => {
  loadAccounts()
  loadIncome()
  loadPlaidLinks()
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
                <td class="px-5 py-3 text-center">
                  <span :class="acct.is_active ? 'text-green-600 dark:text-green-400' : 'text-gray-400'">
                    {{ acct.is_active ? 'Yes' : 'No' }}
                  </span>
                </td>
                <td class="px-5 py-3 text-right font-medium text-gray-900 dark:text-white">
                  {{ acct.current_balance != null ? currency(acct.current_balance) : '\u2014' }}
                </td>
                <td class="px-5 py-3 text-right">
                  <button @click="startEditAccount(acct)" class="text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 text-sm font-medium">
                    Edit
                  </button>
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
              <td colspan="7" class="px-5 py-8 text-center text-gray-500 dark:text-gray-400">
                No accounts found
              </td>
            </tr>
          </tbody>
        </table>
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

    <!-- ═══ Email Tab ═══ -->
    <div v-if="activeTab === 'email'" class="space-y-4">
      <!-- Instructions -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-1">Email Receipt Import</h3>
        <p class="text-xs text-gray-500 dark:text-gray-400">
          Forward receipts from Amazon, PayPal, or any merchant to <span class="font-mono text-indigo-600 dark:text-indigo-400">receipts@tallied.dev</span> and they'll be automatically parsed into transactions.
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
