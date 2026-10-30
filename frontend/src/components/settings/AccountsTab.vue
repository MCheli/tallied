<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../../api/client'
import { useFormatters } from '../../composables/useFormatters'
import type { AccountWithBalance } from '../../types'

const { currency, date: fmtDate } = useFormatters()

/** A synced balance more than a week old: the bank connection has stopped updating it. */
function isStale(acct: AccountWithBalance): boolean {
  if (acct.source !== 'simplefin' || !acct.balance_date) return false
  return (Date.now() - new Date(acct.balance_date).getTime()) / 86_400_000 > 7
}

const accounts = ref<AccountWithBalance[]>([])
const loading = ref(false)
const loadError = ref<string | null>(null)
const formError = ref<string | null>(null)
const editingAccountId = ref<string | null>(null)
const showNewAccountForm = ref(false)

const accountTypes = ['cash', 'investment_401k', 'investment_stock', 'real_estate', 'loan_mortgage', 'loan_student', 'credit_card']
const displayGroups = ['Cash', 'Investments', 'Retirement', 'Home Equity', 'Credit Cards', 'Other Loans']

function sourceLabel(source: string): string {
  return source === 'simplefin' ? 'SimpleFIN' : 'Manual'
}

function sourceBadgeClass(source: string): string {
  return source === 'simplefin'
    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400'
    : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
}

const emptyAccountForm = () => ({
  id: '',
  name: '',
  institution: '',
  account_type: 'cash',
  display_group: 'Cash',
  include_in_nw: true,
  is_active: true,
  notes: '',
})

const accountForm = ref(emptyAccountForm())
const editAccountForm = ref(emptyAccountForm())

async function loadAccounts() {
  loading.value = true
  loadError.value = null
  try {
    accounts.value = await api.getAccounts()
  } catch (e) {
    loadError.value = 'Failed to load accounts: ' + (e instanceof Error ? e.message : String(e))
  }
  loading.value = false
}

function startEditAccount(acct: AccountWithBalance) {
  formError.value = null
  editingAccountId.value = acct.id
  editAccountForm.value = {
    id: acct.id,
    name: acct.name,
    institution: acct.institution || '',
    account_type: acct.account_type,
    display_group: acct.display_group,
    include_in_nw: acct.include_in_nw,
    is_active: acct.is_active,
    notes: acct.notes || '',
  }
}

function cancelEditAccount() {
  editingAccountId.value = null
}

async function saveEditAccount() {
  if (!editingAccountId.value) return
  formError.value = null
  try {
    await api.updateAccount(editingAccountId.value, {
      name: editAccountForm.value.name,
      institution: editAccountForm.value.institution || null,
      account_type: editAccountForm.value.account_type,
      display_group: editAccountForm.value.display_group,
      include_in_nw: editAccountForm.value.include_in_nw,
      is_active: editAccountForm.value.is_active,
      notes: editAccountForm.value.notes || null,
    })
    editingAccountId.value = null
    await loadAccounts()
  } catch (e) {
    formError.value = 'Failed to update account: ' + (e instanceof Error ? e.message : String(e))
  }
}

async function saveNewAccount() {
  formError.value = null
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
    formError.value = 'Failed to create account: ' + (e instanceof Error ? e.message : String(e))
  }
}

function cancelNewAccount() {
  showNewAccountForm.value = false
  accountForm.value = emptyAccountForm()
  formError.value = null
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
    deleteError.value = 'Failed to load related record counts: ' + (e instanceof Error ? e.message : String(e))
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
    deleteError.value = 'Failed to delete account: ' + (e instanceof Error ? e.message : String(e))
    deleteBusy.value = false
  }
}

onMounted(loadAccounts)

const inputClass = 'w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white'
const cellInputClass = 'w-full min-w-[8rem] px-2 py-1 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white'
</script>

<template>
  <div class="min-w-0 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
    <div class="flex flex-wrap items-center justify-between gap-2 px-5 py-4 border-b border-gray-200 dark:border-gray-800">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Accounts</h3>
      <button
        @click="showNewAccountForm ? cancelNewAccount() : (showNewAccountForm = true)"
        class="px-3 py-1.5 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium"
      >
        {{ showNewAccountForm ? 'Cancel' : 'Add Account' }}
      </button>
    </div>

    <!-- New Account Form -->
    <div v-if="showNewAccountForm" class="px-5 py-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
      <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">ID (optional)</label>
          <input v-model="accountForm.id" :class="inputClass" placeholder="Auto-generated" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Name</label>
          <input v-model="accountForm.name" :class="inputClass" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Institution</label>
          <input v-model="accountForm.institution" :class="inputClass" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Type</label>
          <select v-model="accountForm.account_type" :class="inputClass">
            <option v-for="t in accountTypes" :key="t" :value="t">{{ t }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Display Group</label>
          <select v-model="accountForm.display_group" :class="inputClass">
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
          <input v-model="accountForm.notes" :class="inputClass" />
        </div>
        <div class="flex items-end gap-2">
          <button @click="saveNewAccount" class="px-3 py-1.5 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium">Save</button>
          <button @click="cancelNewAccount" class="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">Cancel</button>
        </div>
      </div>
    </div>

    <div v-if="formError" class="px-5 py-3 text-sm text-red-600 dark:text-red-400 border-b border-gray-100 dark:border-gray-800">{{ formError }}</div>
    <div v-if="loadError" class="px-5 py-3 text-sm text-red-600 dark:text-red-400">{{ loadError }}</div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center h-32">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
    </div>

    <!-- Table: scrolls inside its own container on narrow screens -->
    <div v-else class="overflow-x-auto min-w-0">
      <table class="w-full min-w-[56rem] text-sm">
        <thead>
          <tr class="border-b border-gray-100 dark:border-gray-800">
            <th class="text-left px-3 py-3 font-medium text-gray-500 dark:text-gray-400">Name</th>
            <th class="text-left px-3 py-3 font-medium text-gray-500 dark:text-gray-400">Institution</th>
            <th class="text-left px-3 py-3 font-medium text-gray-500 dark:text-gray-400">Type</th>
            <th class="text-left px-3 py-3 font-medium text-gray-500 dark:text-gray-400">Group</th>
            <th class="text-left px-3 py-3 font-medium text-gray-500 dark:text-gray-400">Source</th>
            <th class="text-center px-3 py-3 font-medium text-gray-500 dark:text-gray-400">In NW</th>
            <th class="text-center px-3 py-3 font-medium text-gray-500 dark:text-gray-400">Active</th>
            <th class="text-right px-3 py-3 font-medium text-gray-500 dark:text-gray-400">Balance</th>
            <th class="text-right px-3 py-3 font-medium text-gray-500 dark:text-gray-400"></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="acct in accounts" :key="acct.id">
            <!-- Display Row -->
            <tr v-if="editingAccountId !== acct.id" class="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
              <td class="px-3 py-3 text-gray-900 dark:text-white max-w-[16rem]">
                <div class="min-w-0 truncate" :title="acct.name">{{ acct.name }}</div>
              </td>
              <td class="px-3 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{{ acct.institution || '—' }}</td>
              <td class="px-3 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{{ acct.account_type }}</td>
              <td class="px-3 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{{ acct.display_group }}</td>
              <td class="px-3 py-3">
                <span class="inline-block px-2 py-0.5 text-xs rounded font-medium" :class="sourceBadgeClass(acct.source)">
                  {{ sourceLabel(acct.source) }}
                </span>
              </td>
              <td class="px-3 py-3 text-center">
                <span :class="acct.include_in_nw ? 'text-green-600 dark:text-green-400' : 'text-gray-400'">
                  {{ acct.include_in_nw ? 'Yes' : 'No' }}
                </span>
              </td>
              <td class="px-3 py-3 text-center">
                <span :class="acct.is_active ? 'text-green-600 dark:text-green-400' : 'text-gray-400'">
                  {{ acct.is_active ? 'Yes' : 'No' }}
                </span>
              </td>
              <td class="px-3 py-3 text-right font-medium text-gray-900 dark:text-white whitespace-nowrap">
                {{ acct.current_balance != null ? currency(acct.current_balance) : '—' }}
                <div v-if="acct.balance_date" class="text-xs font-normal" :class="isStale(acct) ? 'text-amber-600 dark:text-amber-400' : 'text-gray-400'"
                  :title="isStale(acct) ? 'The bank connection has not updated this balance for over a week' : undefined">
                  {{ isStale(acct) ? 'stale · ' : '' }}{{ fmtDate(acct.balance_date) }}
                </div>
              </td>
              <td class="px-3 py-3 text-right">
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
                <input v-model="editAccountForm.name" :class="cellInputClass" />
              </td>
              <td class="px-5 py-2">
                <input v-model="editAccountForm.institution" :class="cellInputClass" />
              </td>
              <td class="px-5 py-2">
                <select v-model="editAccountForm.account_type" :class="cellInputClass">
                  <option v-for="t in accountTypes" :key="t" :value="t">{{ t }}</option>
                </select>
              </td>
              <td class="px-5 py-2">
                <select v-model="editAccountForm.display_group" :class="cellInputClass">
                  <option v-for="g in displayGroups" :key="g" :value="g">{{ g }}</option>
                </select>
              </td>
              <td class="px-5 py-2 text-gray-400 text-xs">—</td>
              <td class="px-5 py-2 text-center">
                <input type="checkbox" v-model="editAccountForm.include_in_nw" class="rounded" title="Include in net worth" />
              </td>
              <td class="px-5 py-2 text-center">
                <input type="checkbox" v-model="editAccountForm.is_active" class="rounded" title="Active" />
              </td>
              <td class="px-5 py-2 text-right text-gray-400 text-sm">—</td>
              <td class="px-5 py-2 text-right">
                <div class="flex gap-1 justify-end">
                  <button @click="saveEditAccount" class="px-2 py-1 text-xs rounded bg-indigo-600 text-white hover:bg-indigo-700 transition-colors">Save</button>
                  <button @click="cancelEditAccount" class="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">Cancel</button>
                </div>
              </td>
            </tr>
          </template>
          <tr v-if="accounts.length === 0 && !loading">
            <td colspan="9" class="px-5 py-8 text-center text-gray-500 dark:text-gray-400">
              No accounts found
            </td>
          </tr>
        </tbody>
      </table>
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
  </div>
</template>
