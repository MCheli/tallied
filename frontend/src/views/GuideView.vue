<script setup lang="ts">
import { reactive } from 'vue'

const wealthLayers = [
  {
    name: 'Cash',
    icon: '💵',
    badge: 'Most liquid',
    badgeClass: 'bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300',
    description: 'Checking, savings, money market. Available immediately with no tax consequence.',
    examples: 'Chase checking, HYSA, Fidelity cash',
  },
  {
    name: 'Investments',
    icon: '📈',
    badge: 'Liquid',
    badgeClass: 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300',
    description: 'Taxable brokerage accounts and company stock. Can be sold and accessed within days, but may trigger capital gains tax.',
    examples: 'E-Trade brokerage, vested RSUs',
  },
  {
    name: 'Home Equity',
    icon: '🏠',
    badge: 'Illiquid',
    badgeClass: 'bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300',
    description: 'Property value minus mortgage balance. Real but not accessible without selling or refinancing.',
    examples: 'Home value ($658K) − mortgage balance ($440K) = $218K equity',
  },
  {
    name: 'Retirement',
    icon: '🏦',
    badge: 'Locked',
    badgeClass: 'bg-purple-100 dark:bg-purple-950 text-purple-700 dark:text-purple-300',
    description: '401(k), IRA, and similar accounts. Growing tax-advantaged but penalized if withdrawn before age 59½.',
    examples: 'Fidelity 401(k), Traditional IRA',
  },
]

const entities = reactive([
  {
    name: 'Accounts',
    table: 'accounts',
    icon: '🏛',
    summary: 'The financial accounts you own — every balance snapshot and transaction is linked to an account.',
    source: 'Manual / Chrome ext.',
    sourceClass: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
    open: false,
    fields: [
      'Name, institution',
      'Type (checking, savings, brokerage, 401k, mortgage, real_estate, credit_card, student_loan)',
      'Display group (which wealth layer it belongs to)',
      'include_in_nw flag (whether it counts toward net worth)',
    ],
    usedFor: [
      'Grouping balance snapshots into wealth layers',
      'Net worth calculation (summing balances across accounts)',
      'Filtering transactions by account',
      'Plaid link association for automatic transaction sync',
    ],
    notUsedFor: null,
    note: 'Account type and display_group determine which layer of net worth the balance appears in. If an account looks wrong in the Dashboard, the display_group is probably misconfigured.',
  },
  {
    name: 'Balance Snapshots',
    table: 'balance_snapshots',
    icon: '📸',
    summary: 'A point-in-time balance reading for one account. Multiple snapshots over time build the net worth trend chart.',
    source: 'Chrome ext. / Monarch import',
    sourceClass: 'bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400',
    open: false,
    fields: [
      'account_id (which account)',
      'snapshot_date',
      'balance (dollar amount)',
      'source (where this reading came from)',
    ],
    usedFor: [
      'Net worth at any point in time',
      'Net worth trend chart (Assets page)',
      'Planning actuals — what was your investment balance in 2025?',
      'Forecast baseline — starting point for future projections',
    ],
    notUsedFor: [
      'Tracking individual transactions (that\'s the transactions table)',
    ],
    note: 'You need at least one snapshot per account per month for the trend chart to look good. The Chrome extension is the intended way to capture these regularly.',
  },
  {
    name: 'Transactions',
    table: 'transactions',
    icon: '💳',
    summary: 'Individual debits and credits — every coffee, paycheck, and transfer. The raw material for spending analysis.',
    source: 'Plaid / Monarch import',
    sourceClass: 'bg-green-50 dark:bg-green-950 text-green-600 dark:text-green-400',
    open: false,
    fields: [
      'date, amount (negative = expense, positive = income)',
      'merchant, category, category_group',
      'is_recurring flag',
      'account_id, source',
      'plaid_transaction_id (for Plaid-sourced records)',
    ],
    usedFor: [
      'Spending by category (Spending page)',
      'Monthly spending trend',
      'Recurring expense detection',
      'Cash flow analysis (income vs outflows)',
      'Searchable transactions table',
    ],
    notUsedFor: [
      'Net worth calculation (that uses balance snapshots, not transactions)',
      'Income tracking for planning (that uses W2 records)',
    ],
    note: 'Plaid syncs transactions automatically once linked and normalizes them into a common format. Monarch historical imports are also normalized on ingest. Positive amounts are income/deposits, negative are expenses.',
  },
  {
    name: 'W2 Records',
    table: 'w2_records',
    icon: '📄',
    summary: 'Annual compensation summary — one row per tax year. The authoritative source for income in the planning model.',
    source: 'W2 PDF upload (AI parsing)',
    sourceClass: 'bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400',
    open: false,
    fields: [
      'tax_year',
      'gross_pay (total compensation before anything)',
      'w2_wages (Box 1 — wages after pretax deductions)',
      'federal_tax, state_tax, social_security, medicare',
      'pretax_401k, roth_401k (contributions that year)',
      'cafeteria_125, transit (pretax benefit deductions)',
      'employer_health (Box 12 DD — employer health insurance cost)',
      'base_salary, rsu_income (breakdown of compensation type)',
    ],
    usedFor: [
      'Income history chart',
      'Planning actuals — what did you actually earn in 2025?',
      'Planning forecast — extrapolating current year income',
      'Tax efficiency analysis (effective tax rate)',
      'Take-home pay calculation for planning table',
    ],
    notUsedFor: null,
    note: 'gross_pay is your total comp BEFORE any deductions. w2_wages (Box 1) is lower because pretax deductions (401k, health, transit) reduce it. The planning table uses gross_pay for income rows and derives take-home from the tax/deduction fields. Currently holds 3 years of data (2023-2025).',
  },
  {
    name: 'RSU Grants & Vest Events',
    table: 'rsu_grants, vest_events, stock_prices',
    icon: '📊',
    summary: 'Equity compensation — grants of PTC stock that vest over time. Each grant has a vesting schedule with cost basis, tax withholding, and short/long-term holding status.',
    source: 'E-Trade spreadsheet export',
    sourceClass: 'bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400',
    open: false,
    fields: [
      'Grant: id, symbol, grant_date, total_shares, vested/unvested/sellable counts',
      'Vest event: vest_date, vest_period, shares, fmv_at_vest (cost basis/share)',
      'Vest event: shares_withheld (for tax), shares_released (net), total_taxes_paid',
      'Tax status: computed from holding period (>1yr from vest = Long Term)',
      'Stock prices: symbol, date, close_price (live from Yahoo Finance, cached daily)',
    ],
    usedFor: [
      'RSU page — grant overview, vesting timeline, tax lot analysis',
      'Current unvested stock value (part of investment balance)',
      'Income breakdown: base salary vs RSU vesting income by year',
      'Unrealized gain/loss tracking with cost basis per vest',
      'Short-term vs long-term capital gains analysis',
    ],
    notUsedFor: null,
    note: 'Data is loaded from E-Trade "Download by Type (expanded)" and "Download by Status (expanded)" spreadsheet exports. Stock price is fetched live from Yahoo Finance and cached daily. To refresh: RSU page → "Reload from E-Trade" button.',
  },
  {
    name: 'Mortgage',
    table: 'mortgages',
    icon: '🏡',
    summary: 'Your home loan — the liability side of home equity. One record, updated as the balance decreases. Imported from mortgage statement PDF upload.',
    source: 'Mortgage PDF upload (AI parsing)',
    sourceClass: 'bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400',
    open: false,
    fields: [
      'rate, monthly_payment',
      'original_amount, origination_date',
      'current_balance (updated each capture)',
      'escrow_payment, principal_payment, interest_payment (payment breakdown)',
      'term_months, loan_type',
    ],
    usedFor: [
      'Home equity = property valuation − current_balance',
      'Planning: mortgage payoff projection',
      'Net worth liability calculation',
      'Property page: amortization schedule chart with "Today" marker',
      'Property page: payment breakdown donut (principal/interest/escrow)',
    ],
    notUsedFor: null,
    note: 'Data is extracted from mortgage statement PDFs via Claude AI parsing. Home equity flows into net worth via the Accounts table — there should be a real_estate account whose balance is updated by property valuations, and a mortgage account whose balance is this current_balance.',
  },
  {
    name: 'Property Valuations',
    table: 'property_valuations',
    icon: '🏘',
    summary: 'Point-in-time estimates of your home\'s value. Like balance snapshots but for real estate.',
    source: 'Manual (Zillow, etc.)',
    sourceClass: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
    open: false,
    fields: [
      'account_id (the real_estate account)',
      'valuation_date, value, source',
    ],
    usedFor: [
      'Home equity calculation (value − mortgage balance)',
      'Net worth trend (real estate layer)',
    ],
    notUsedFor: null,
    note: 'Currently requires manual entry. A future version could pull Zillow estimates automatically.',
  },
  {
    name: 'Plan Versions',
    table: 'plan_versions',
    icon: '🗺',
    summary: 'A named retirement scenario — e.g. "Retire at 60" or "Retire at 45". Each plan has its own set of assumptions and projections.',
    source: 'Created in-app',
    sourceClass: 'bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400',
    open: false,
    fields: [
      'name, scenario_type (base/optimistic/pessimistic/custom)',
      'Assumptions: key-value pairs (retirement_age, comp_growth, investment_return, etc.)',
      'Projections: year-by-year computed values',
    ],
    usedFor: [
      'Planning table — year × metric grid from now to retirement',
      'Scenario comparison (are you ahead or behind this plan?)',
      'Sensitivity analysis — which assumption matters most?',
      'Variance report — actuals vs plan for completed years',
    ],
    notUsedFor: null,
    note: 'The planning table cells are colored by status: green = actuals (past years from real data), amber = forecast (current year extrapolated from YTD), white = plan (future years from assumptions). This lets you see at a glance whether 2026 is tracking ahead or behind.',
  },
  {
    name: 'Vehicles',
    table: 'vehicles',
    icon: '🚗',
    summary: 'Fixed capital assets — vehicles you own. Market value is estimated by Claude AI based on year, make, model, mileage, and condition.',
    source: 'Manual + Claude AI',
    sourceClass: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
    open: false,
    fields: [
      'year, make, model',
      'mileage, condition',
      'estimated_value (AI-generated)',
      'value_date (when estimate was last refreshed)',
    ],
    usedFor: [
      'Assets page — fixed capital asset listing',
      'Net worth contribution (if included)',
      'Value refresh via Claude AI estimation',
    ],
    notUsedFor: null,
    note: 'Vehicle values are estimated by Claude AI based on the details you provide. Use the "Refresh value" button to get an updated estimate. Currently tracking a 1997 GMC Suburban 2500 and a 1996 Mazda B4000.',
  },
  {
    name: 'Plaid Links',
    table: 'plaid_links',
    icon: '🔗',
    summary: 'Connected bank institutions via Plaid. Each link represents one authenticated connection to a financial institution.',
    source: 'Settings page',
    sourceClass: 'bg-green-50 dark:bg-green-950 text-green-600 dark:text-green-400',
    open: false,
    fields: [
      'institution_name, institution_id',
      'access_token (encrypted)',
      'cursor (for incremental transaction sync)',
      'status, last_synced',
    ],
    usedFor: [
      'Automatic transaction sync from linked banks',
      'Account association (linking Plaid accounts to app accounts)',
      'Plaid status indicator on Dashboard',
    ],
    notUsedFor: null,
    note: 'Currently connected to First Platypus Bank (Plaid sandbox). Manage connections in Settings → Plaid account connections.',
  },
])

const pages = [
  {
    name: 'Dashboard',
    data: ['Balance Snapshots', 'Accounts', 'W2 Records', 'RSU Grants', 'Transactions', 'Plaid Links'],
    description: 'Net worth, liquid net worth, RSU holdings, total comp, 12mo change, liquidity layers chart, comp split donut, next vests, last 30 days spending, Plaid status, account details.',
  },
  {
    name: 'Spending',
    data: ['Transactions'],
    description: 'Spending by category, recurring expenses, searchable transactions table, monthly trend. Data from Plaid (automatic sync) and Monarch (historical import).',
  },
  {
    name: 'Accounts',
    data: ['Balance Snapshots', 'Accounts', 'W2 Records', 'Transactions'],
    description: 'Account balances, net worth over time chart, W2 income history, account balance history, monthly cash flow, all accounts table.',
  },
  {
    name: 'Planning',
    data: ['Plan Versions', 'W2 Records', 'Balance Snapshots', 'RSU Grants'],
    description: 'Year-by-metric table from now to retirement with collapsible column groups (Income, Tax & Take-home, Savings, Wealth). Assumptions sidebar with sliders. Clickable rows show "What you need to believe" narrative. Plan comparison with delta columns.',
  },
  {
    name: 'Income',
    data: ['W2 Records'],
    description: 'W2 upload (AI parsing), pay stub upload (AI parsing for salary/RSU split), gross-to-net waterfall, compensation breakdown bar, "where your gross pay goes" stacked chart, comp split chart, year-over-year table. 3 years of W2 data (2023-2025).',
  },
  {
    name: 'RSU',
    data: ['RSU Grants', 'Vest Events', 'Stock Prices'],
    description: 'PTC stock holdings with live Yahoo Finance price. Holdings/sellable/unvested/unrealized gain cards. Stock price chart (5yr). "If You Sold Today" liquidation analysis with tax lots. Upcoming vests with countdown. Vest event value by year. All grants expandable. Import from E-Trade spreadsheet.',
  },
  {
    name: 'Property',
    data: ['Mortgage', 'Property Valuations', 'Accounts'],
    description: 'Mortgage details from statement PDF upload (AI parsing). Property value ($658K Zillow). Equity position with appreciation vs principal paid. Amortization schedule chart with "Today" marker. Payment breakdown donut.',
  },
  {
    name: 'Assets',
    data: ['Vehicles'],
    description: 'Fixed capital assets (vehicles). AI-estimated market values via Claude. Add/edit/delete vehicles. Refresh value button.',
  },
  {
    name: 'Settings',
    data: ['Accounts', 'W2 Records', 'Plaid Links'],
    description: 'Accounts management, Income/W2 editing, Plaid account connections (connect bank, sync transactions), import history.',
  },
  {
    name: 'Admin',
    data: ['All tables'],
    description: 'Raw database table browser with row counts.',
  },
  {
    name: 'Guide',
    data: [],
    description: 'This page — reference documentation for the data model, features, and data flow.',
  },
]

const dataSources = [
  {
    name: 'Plaid',
    icon: '🔗',
    description: 'Automatic transaction sync from linked bank accounts. Set up once in Settings and sync on demand. Currently connected: First Platypus Bank (sandbox).',
    feeds: 'Transactions, Account balances',
  },
  {
    name: 'Chrome Extension',
    icon: '🔌',
    description: 'Screenshot any financial page — Claude AI extracts values and presents them for confirmation. Used for account balances and other captures.',
    feeds: 'Balance snapshots',
  },
  {
    name: 'W2 / Pay Stub PDF Upload',
    icon: '📄',
    description: 'Upload W2 or pay stub PDFs directly. Claude AI parses income, tax fields, salary/RSU split, deductions. Supports 2023-2025 W2s.',
    feeds: 'W2 records (Income page)',
  },
  {
    name: 'Mortgage Statement PDF',
    icon: '🏡',
    description: 'Upload mortgage statement PDF. Claude AI extracts balance, rate, payment details, escrow breakdown.',
    feeds: 'Mortgage record (Property page)',
  },
  {
    name: 'E-Trade Spreadsheet',
    icon: '📊',
    description: 'Upload E-Trade "Download by Type (expanded)" and "Download by Status (expanded)" spreadsheet exports for RSU grant and vest data.',
    feeds: 'RSU grants, Vest events',
  },
  {
    name: 'Yahoo Finance',
    icon: '📈',
    description: 'Live PTC stock price fetched automatically and cached daily. Powers current holdings value and stock price chart.',
    feeds: 'Stock prices (RSU page)',
  },
  {
    name: 'Claude AI',
    icon: '🤖',
    description: 'Vehicle market value estimation based on year, make, model, mileage, and condition. Also powers W2, pay stub, and mortgage PDF parsing.',
    feeds: 'Vehicle valuations, PDF data extraction',
  },
  {
    name: 'Manual / Import',
    icon: '📥',
    description: 'CSV import from Monarch Money, manual entry via Settings, property valuations, vehicle details, account creation.',
    feeds: 'Transactions, Balance snapshots, Accounts, Property valuations, Vehicles',
  },
]
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-10">

    <div>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">How This App Works</h1>
      <p class="mt-2 text-gray-500 dark:text-gray-400 text-sm">
        A reference guide to the data model, what each piece means, and how it all connects.
      </p>
    </div>

    <!-- The Big Picture -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">The Big Picture</h2>
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6 text-sm text-gray-700 dark:text-gray-300 space-y-3 leading-relaxed">
        <p>
          This app is a comprehensive personal finance dashboard that tracks <strong class="text-gray-900 dark:text-white">net worth, income, spending, investments, property, and retirement planning</strong> in one place.
          It answers: are you on track to retire when you want to — and where does all your money actually go?
        </p>
        <p>
          The core loop is: <strong class="text-gray-900 dark:text-white">capture real data → understand your position → compare to your plan → adjust assumptions → repeat.</strong>
          Data flows in from many sources: Plaid (automatic bank sync), PDF uploads parsed by Claude AI (W2s, pay stubs, mortgage statements), E-Trade spreadsheet exports (RSU grants), Yahoo Finance (live stock prices), and manual entry.
          The Planning page ties it all together as a year-by-year table from now until retirement.
        </p>
      </div>
    </section>

    <!-- Wealth Layers -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">How Wealth Is Organized</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
        Net worth is broken into four layers ordered by how quickly you can access the money.
      </p>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div v-for="layer in wealthLayers" :key="layer.name"
          class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-lg">{{ layer.icon }}</span>
            <span class="font-semibold text-gray-900 dark:text-white text-sm">{{ layer.name }}</span>
            <span class="ml-auto text-xs px-2 py-0.5 rounded-full font-medium" :class="layer.badgeClass">{{ layer.badge }}</span>
          </div>
          <p class="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{{ layer.description }}</p>
          <div class="mt-2 text-xs text-indigo-600 dark:text-indigo-400">{{ layer.examples }}</div>
        </div>
      </div>
    </section>

    <!-- Data Entities -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Data Entities</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
        Each entity below is a table in the database. This is the raw material the app works with.
      </p>
      <div class="space-y-3">
        <div v-for="entity in entities" :key="entity.name"
          class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
          <button
            class="w-full text-left px-5 py-4 flex items-start gap-4"
            @click="entity.open = !entity.open"
          >
            <span class="text-xl mt-0.5">{{ entity.icon }}</span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-semibold text-gray-900 dark:text-white text-sm">{{ entity.name }}</span>
                <span class="text-xs font-mono text-gray-400 dark:text-gray-500">{{ entity.table }}</span>
                <span class="ml-auto text-xs px-2 py-0.5 rounded-full" :class="entity.sourceClass">{{ entity.source }}</span>
              </div>
              <p class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{{ entity.summary }}</p>
            </div>
            <span class="text-gray-400 text-xs mt-1">{{ entity.open ? '▲' : '▼' }}</span>
          </button>
          <div v-if="entity.open" class="px-5 pb-5 border-t border-gray-100 dark:border-gray-800">
            <div class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
              <div>
                <div class="font-medium text-gray-700 dark:text-gray-300 mb-2">What it stores</div>
                <ul class="space-y-1 text-gray-500 dark:text-gray-400">
                  <li v-for="field in entity.fields" :key="field" class="flex gap-2">
                    <span class="text-gray-300 dark:text-gray-600">–</span>{{ field }}
                  </li>
                </ul>
              </div>
              <div class="space-y-4">
                <div>
                  <div class="font-medium text-gray-700 dark:text-gray-300 mb-1">Used for</div>
                  <ul class="space-y-1 text-gray-500 dark:text-gray-400">
                    <li v-for="use in entity.usedFor" :key="use" class="flex gap-2">
                      <span class="text-indigo-400">→</span>{{ use }}
                    </li>
                  </ul>
                </div>
                <div v-if="entity.notUsedFor">
                  <div class="font-medium text-gray-700 dark:text-gray-300 mb-1">Not currently used for</div>
                  <ul class="space-y-1 text-gray-500 dark:text-gray-400">
                    <li v-for="n in entity.notUsedFor" :key="n" class="flex gap-2">
                      <span class="text-amber-400">✗</span>{{ n }}
                    </li>
                  </ul>
                </div>
                <div v-if="entity.note" class="text-xs bg-amber-50 dark:bg-amber-950 text-amber-800 dark:text-amber-300 rounded-lg px-3 py-2">
                  {{ entity.note }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- How pages use the data -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">What Each Page Uses</h2>
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-100 dark:border-gray-800">
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400 w-32">Page</th>
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Primary data</th>
              <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">What it shows</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="page in pages" :key="page.name"
              class="border-b border-gray-50 dark:border-gray-800 last:border-0">
              <td class="px-5 py-3 font-medium text-gray-900 dark:text-white">{{ page.name }}</td>
              <td class="px-5 py-3">
                <div class="flex flex-wrap gap-1">
                  <span v-for="d in page.data" :key="d"
                    class="text-xs px-2 py-0.5 bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 rounded-full">
                    {{ d }}
                  </span>
                </div>
              </td>
              <td class="px-5 py-3 text-gray-500 dark:text-gray-400">{{ page.description }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Data Flow -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">How Data Gets In</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <div v-for="source in dataSources" :key="source.name"
          class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="font-semibold text-gray-900 dark:text-white text-sm mb-1">{{ source.icon }} {{ source.name }}</div>
          <p class="text-xs text-gray-500 dark:text-gray-400 leading-relaxed mb-2">{{ source.description }}</p>
          <div class="text-xs text-gray-400 dark:text-gray-500">
            <span class="font-medium">Feeds:</span> {{ source.feeds }}
          </div>
        </div>
      </div>
    </section>

  </div>
</template>

