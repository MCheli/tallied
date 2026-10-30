<script setup lang="ts">
import { reactive } from 'vue'
import PageHeader from '../components/common/PageHeader.vue'

const expandedSections = reactive<Record<string, boolean>>({})

function toggle(key: string) {
  expandedSections[key] = !expandedSections[key]
}

const navGroups = [
  { name: 'Overview', icon: '🏠', pages: ['Dashboard', 'Weekly Recap', 'Guide'] },
  { name: 'Money', icon: '💰', pages: ['Spending', 'Income', 'Cash'] },
  { name: 'Investments', icon: '📈', pages: ['RSU', '401(k)'] },
  { name: 'Property', icon: '🏡', pages: ['Property', 'Assets'] },
  { name: 'Planning', icon: '🗺', pages: ['Planning'] },
  { name: 'Platform', icon: '⚙️', pages: ['Database', 'API', 'Settings', 'Admin Portal'], note: 'Admin Portal is admin-only' },
]

const platformFeatures = [
  {
    name: 'One household, one database',
    icon: '🏢',
    description: 'All financial data lives in a dedicated PostgreSQL schema that the owner can also open with psql or a spreadsheet. The multi-tenant structure keeps it isolated; it is not a sign-up product.',
  },
  {
    name: 'Google SSO',
    icon: '🔐',
    description: 'Sign in with Google in production, email/password in local development. New Google users wait in a pending state until an admin approves them.',
  },
  {
    name: 'API keys',
    icon: '🔑',
    description: 'Create keys on the API page for scripts. Pass them in the X-API-Key header. A read key can only read; a write key is needed for anything that changes data.',
  },
  {
    name: 'SQL transparency',
    icon: '🔍',
    description: 'Every tile has an info icon that explains the number and a </> button (tap it on a phone, hover on a desktop) that shows the query behind it.',
  },
  {
    name: 'Import workflow',
    icon: '📤',
    description: 'Upload a PDF, Excel or CSV. Claude proposes changes field by field; nothing is written until you accept them. Ask the review chat to add or correct a value.',
  },
  {
    name: 'API reference',
    icon: '📖',
    description: 'The interactive OpenAPI reference is served at /api/v1/scalar and linked from the API page.',
  },
  {
    name: 'Admin Portal',
    icon: '🛡',
    description: 'Approve pending users, toggle admin and active flags, and see tenant stats. Admin-only; kept working, not extended.',
  },
  {
    name: 'Database explorer',
    icon: '🗄',
    description: 'An ERD of your schema, row previews, column descriptions and a read-only SQL runner confined to your own schema. Desktop only.',
  },
]

const pages = [
  {
    name: 'Dashboard',
    group: 'Overview',
    description: 'What you are worth right now: net worth and liquid net worth from the latest balance per account, the liquidity layers (cash, investments, home equity, retirement, liabilities), the compensation split, net worth over time, the next RSU vests and the last 30 days of spending.',
  },
  {
    name: 'Weekly Recap',
    group: 'Overview',
    description: 'One Sunday–Saturday week at a glance, worked out from your data whenever it is opened (no AI, nothing stored): net worth change, spending against the four weeks before, the biggest categories and purchases, income, and the bills and RSU vests due the week after. Opens on the last completed week; earlier weeks are one click back.',
  },
  {
    name: 'Spending',
    group: 'Money',
    description: 'Where money went in a period: spending by category, recurring merchants, the transaction table and the monthly trend. One date range and one account filter scope the whole page. Transfers and loan payments are not spending.',
  },
  {
    name: 'Income',
    group: 'Money',
    description: 'For a tax year, how gross pay splits into salary and RSU and where it goes: tax, 401(k), benefits, take-home. One definition of take-home across the tiles, the waterfall and the year-over-year table.',
  },
  {
    name: 'Cash',
    group: 'Money',
    description: 'Checking and savings balances, their trend, months of runway, and the notable transactions behind the movements. The time range scopes every section; Sync runs a SimpleFIN sync.',
  },
  {
    name: 'RSU',
    group: 'Investments',
    description: 'What the company stock is worth, what selling the vested shares today would net after tax, when the rest vests, and every grant with its vest events. Prices come from Yahoo Finance once a day.',
  },
  {
    name: '401(k)',
    group: 'Investments',
    description: 'Balance and its Roth / pre-tax / employer-match split, contribution rates (editable here), holdings with live prices, and the balance history built from imported statements.',
  },
  {
    name: 'Property',
    group: 'Property',
    description: 'Value, mortgage balance, equity, the amortization schedule and the payment split. Valuations you type are never overwritten; AI projections are drawn dashed and labelled as estimates.',
  },
  {
    name: 'Assets',
    group: 'Property',
    description: 'Vehicles with a labelled AI estimate of their value (source, model, confidence and reasoning shown), depreciation since purchase, and a value history. Adding a vehicle never depends on the AI being available.',
  },
  {
    name: 'Planning',
    group: 'Planning',
    description: 'Will it work, and what would need to be true? From your balances, pay and actual spending: chance of success (simulated and historical), wealth bands with the 55 / 59½ / 62 / 65 / 67 / 70 milestones, retirement ages compared, what retirement costs, how the early years are paid, the nest egg each withdrawal rule needs, macro scenarios, acquisition and layoff shocks, a sprint-to-retirement grid and the levers that matter most. Levers are what-ifs until you save.',
  },
  {
    name: 'Database',
    group: 'Platform',
    description: 'ERD, table previews, column documentation, a read-only SQL runner confined to your schema, and direct-connection credentials for psql or Excel. Needs a desktop-width screen.',
  },
  {
    name: 'API',
    group: 'Platform',
    description: 'API keys with read/write scopes, usage, outbound webhooks, and a link to the interactive reference at /api/v1/scalar.',
  },
  {
    name: 'Settings',
    group: 'Platform',
    description: 'Accounts, Income (every W-2 field), the SimpleFIN connection with per-account sync options, Email Receipts (registered sender addresses and the receipt log), and Import History.',
  },
  {
    name: 'Admin Portal',
    group: 'Platform',
    description: 'User approval and tenant management. Admin-only.',
  },
  {
    name: 'Guide',
    group: 'Overview',
    description: 'This page: what each page is for and how data gets in.',
  },
]

const dataSources = [
  {
    name: 'SimpleFIN',
    icon: '🏦',
    description: 'The bank connection. Paste a SimpleFIN setup token in Settings, choose which accounts sync balances and transactions, and it runs every 12 hours or on demand.',
    feeds: 'Accounts, balances, transactions',
  },
  {
    name: 'Document import',
    icon: '📄',
    description: 'Upload W-2s, pay stubs, mortgage statements, 401(k) statements or E-Trade RSU exports. Claude reads the document and proposes changes you review before anything is saved.',
    feeds: 'W-2 records, mortgage, 401(k), RSU grants and vests',
  },
  {
    name: 'Email receipts',
    icon: '✉️',
    description: 'Forward an order confirmation from an address you registered in Settings and it becomes a transaction. Receipts from unregistered senders are rejected.',
    feeds: 'Transactions',
  },
  {
    name: 'Yahoo Finance',
    icon: '📈',
    description: 'Stock and fund prices, fetched once a day per symbol. Powers the RSU values, the price chart and 401(k) holding prices.',
    feeds: 'Stock prices',
  },
  {
    name: 'Manual entry',
    icon: '✏️',
    description: 'Accounts and W-2 fields in Settings, vehicles on Assets, property valuations on Property, plan assumptions on Planning, and a row editor on the Database page for corrections.',
    feeds: 'Everything else',
  },
]

const wealthLayers = [
  {
    name: 'Cash',
    icon: '💵',
    badge: 'Most liquid',
    badgeClass: 'bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300',
    description: 'Checking, savings, money market. Available immediately with no tax consequence.',
  },
  {
    name: 'Investments',
    icon: '📈',
    badge: 'Liquid',
    badgeClass: 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300',
    description: 'Taxable brokerage accounts and company stock. Can be sold within days, but may trigger capital gains tax.',
  },
  {
    name: 'Home Equity',
    icon: '🏠',
    badge: 'Illiquid',
    badgeClass: 'bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300',
    description: 'Property value minus mortgage balance. Real but not accessible without selling or refinancing.',
  },
  {
    name: 'Retirement',
    icon: '🏦',
    badge: 'Locked',
    badgeClass: 'bg-purple-100 dark:bg-purple-950 text-purple-700 dark:text-purple-300',
    description: '401(k), IRA, and similar accounts. Growing tax-advantaged but penalized if withdrawn before 59 and a half.',
  },
]

const importSteps = [
  { title: '1. Upload', text: 'Drop a PDF, Excel or CSV into the import modal from the page that owns the data (Income, Property, RSU, 401(k)).' },
  { title: '2. Extract', text: 'Claude reads the document into the fields that page tracks and nothing else.' },
  { title: '3. Review', text: 'Every proposed change shows the current and new value. Untick what you do not want; ask the chat to add or correct a value.' },
  { title: '4. Confirm', text: 'Accepted changes are written and listed under Settings → Import History. Nothing is saved before this step.' },
]
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-10 min-w-0">

    <PageHeader title="Tallied Guide" subtitle="What each page is for, how data gets in, and how the platform pieces fit together." />

    <!-- The Big Picture -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">The Big Picture</h2>
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 sm:p-6 text-sm text-gray-700 dark:text-gray-300 space-y-3 leading-relaxed">
        <p>
          <strong class="text-gray-900 dark:text-white">Tallied</strong> is one household's finance dashboard. It keeps
          <strong class="text-gray-900 dark:text-white">accounts, transactions, income, company stock, 401(k), property and vehicles</strong>
          in one database, shows what that adds up to, and projects it forward to retirement.
        </p>
        <p>
          The loop is: <strong class="text-gray-900 dark:text-white">feed real data &rarr; understand the position &rarr; compare to the plan &rarr; adjust assumptions &rarr; repeat.</strong>
          Data comes in from SimpleFIN (bank sync), document import (Claude reads statements), email receipts, Yahoo Finance prices, and manual entry.
          Every number can be explained: each tile has an info icon saying what it is and what feeds it, and a button showing the query behind it.
        </p>
      </div>
    </section>

    <!-- Navigation -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Navigation</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">Pages are organized into six groups in the sidebar.</p>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <div v-for="group in navGroups" :key="group.name"
          class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="font-semibold text-gray-900 dark:text-white text-sm mb-2">{{ group.icon }} {{ group.name }}</div>
          <ul class="text-xs text-gray-500 dark:text-gray-400 space-y-1">
            <li v-for="page in group.pages" :key="page" class="flex gap-2">
              <span class="text-gray-300 dark:text-gray-600">&ndash;</span>{{ page }}
            </li>
          </ul>
          <div v-if="group.note" class="mt-2 text-xs text-amber-600 dark:text-amber-400">{{ group.note }}</div>
        </div>
      </div>
    </section>

    <!-- Platform Features -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Platform Features</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">The pieces around the financial pages. They must keep working; they are not where new features go.</p>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div v-for="feature in platformFeatures" :key="feature.name"
          class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 min-w-0">
          <div class="font-semibold text-gray-900 dark:text-white text-sm mb-1">{{ feature.icon }} {{ feature.name }}</div>
          <p class="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{{ feature.description }}</p>
        </div>
      </div>
    </section>

    <!-- Wealth Layers -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">How Wealth Is Organized</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">Net worth is broken into layers ordered by how quickly you can access the money. Credit cards and other loans show as negative layers.</p>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div v-for="layer in wealthLayers" :key="layer.name"
          class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="flex items-center gap-2 mb-2 flex-wrap">
            <span class="text-lg">{{ layer.icon }}</span>
            <span class="font-semibold text-gray-900 dark:text-white text-sm">{{ layer.name }}</span>
            <span class="ml-auto text-xs px-2 py-0.5 rounded-full font-medium" :class="layer.badgeClass">{{ layer.badge }}</span>
          </div>
          <p class="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{{ layer.description }}</p>
        </div>
      </div>
    </section>

    <!-- Pages -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Pages</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">What each page shows and what it is for.</p>
      <div class="space-y-3">
        <div v-for="page in pages" :key="page.name"
          class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
          <button
            class="w-full text-left px-4 sm:px-5 py-3.5 min-h-[44px] flex items-start gap-4"
            :aria-expanded="!!expandedSections[page.name]"
            @click="toggle(page.name)"
          >
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-semibold text-gray-900 dark:text-white text-sm">{{ page.name }}</span>
                <span class="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400">{{ page.group }}</span>
              </div>
            </div>
            <span class="text-gray-400 text-xs mt-1">{{ expandedSections[page.name] ? '&#9650;' : '&#9660;' }}</span>
          </button>
          <div v-if="expandedSections[page.name]" class="px-4 sm:px-5 pb-4 border-t border-gray-100 dark:border-gray-800">
            <p class="mt-3 text-sm text-gray-500 dark:text-gray-400 leading-relaxed">{{ page.description }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Data Sources -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">How Data Gets In</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">Five sources feed Tallied. Monarch and Plaid were removed in October 2026.</p>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <div v-for="source in dataSources" :key="source.name"
          class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 min-w-0">
          <div class="font-semibold text-gray-900 dark:text-white text-sm mb-1">{{ source.icon }} {{ source.name }}</div>
          <p class="text-xs text-gray-500 dark:text-gray-400 leading-relaxed mb-2">{{ source.description }}</p>
          <div class="text-xs text-gray-400 dark:text-gray-500">
            <span class="font-medium">Feeds:</span> {{ source.feeds }}
          </div>
        </div>
      </div>
    </section>

    <!-- Import Workflow -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Import Workflow</h2>
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 sm:p-6">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
          <div v-for="s in importSteps" :key="s.title" class="min-w-0">
            <div class="text-base font-semibold text-gray-900 dark:text-white mb-1">{{ s.title }}</div>
            <p class="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{{ s.text }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Getting Started -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Getting Started</h2>
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 sm:p-6 text-sm text-gray-700 dark:text-gray-300 space-y-2 leading-relaxed">
        <p><strong class="text-gray-900 dark:text-white">1.</strong> Sign in. New Google accounts are approved by an admin first.</p>
        <p><strong class="text-gray-900 dark:text-white">2.</strong> In Settings, connect SimpleFIN and choose which accounts sync balances and transactions.</p>
        <p><strong class="text-gray-900 dark:text-white">3.</strong> Import your W-2s on the Income page.</p>
        <p><strong class="text-gray-900 dark:text-white">4.</strong> Import your mortgage statement on the Property page and add a valuation.</p>
        <p><strong class="text-gray-900 dark:text-white">5.</strong> Import the E-Trade RSU export on the RSU page and a 401(k) statement on the 401(k) page.</p>
        <p><strong class="text-gray-900 dark:text-white">6.</strong> Add vehicles on the Assets page and request an estimate.</p>
        <p><strong class="text-gray-900 dark:text-white">7.</strong> Register your email address under Settings → Email Receipts and forward receipts to the household address.</p>
        <p><strong class="text-gray-900 dark:text-white">8.</strong> Create a plan on the Planning page and tune the assumptions.</p>
      </div>
    </section>

  </div>
</template>
