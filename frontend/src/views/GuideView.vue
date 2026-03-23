<script setup lang="ts">
import { reactive } from 'vue'

const expandedSections = reactive<Record<string, boolean>>({})

function toggle(key: string) {
  expandedSections[key] = !expandedSections[key]
}

const navGroups = [
  {
    name: 'Overview',
    icon: '🏠',
    pages: ['Dashboard', 'Guide'],
  },
  {
    name: 'Money',
    icon: '💰',
    pages: ['Spending', 'Income', 'Cash'],
  },
  {
    name: 'Investments',
    icon: '📈',
    pages: ['RSU', '401(k)'],
  },
  {
    name: 'Property',
    icon: '🏡',
    pages: ['Property', 'Assets'],
  },
  {
    name: 'Planning',
    icon: '🗺',
    pages: ['Planning'],
  },
  {
    name: 'Platform',
    icon: '⚙️',
    pages: ['Database', 'API', 'Settings', 'Admin Portal'],
    note: 'Admin Portal is admin-only',
  },
]

const platformFeatures = [
  {
    name: 'Multi-tenancy',
    icon: '🏢',
    description: 'Each user gets their own isolated data space (tenant). All financial data is scoped to your tenant so nothing leaks between users.',
  },
  {
    name: 'Google SSO',
    icon: '🔐',
    description: 'Sign in with your Google account. New users are placed in a pending state and need admin approval before they can access the app.',
  },
  {
    name: 'API Keys',
    icon: '🔑',
    description: 'Generate API keys for programmatic access. Pass your key via the X-API-Key header. Manage keys on the API page.',
  },
  {
    name: 'SQL Transparency',
    icon: '🔍',
    description: 'Hover over any metric tile to reveal a </> icon. Click it to see the exact SQL query that produced the number. No black boxes.',
  },
  {
    name: 'Import Workflow',
    icon: '📤',
    description: 'Upload PDFs or Excel files. AI parses them and shows you the extracted changes for review. Chat with AI to correct mistakes, then confirm to apply.',
  },
  {
    name: 'API Reference',
    icon: '📖',
    description: 'Scalar-powered interactive API docs available at /developer. Try endpoints directly from the browser with your API key.',
  },
  {
    name: 'Admin Portal',
    icon: '🛡',
    description: 'User management, tenant management, and pending user approvals. Only accessible to admin users.',
  },
  {
    name: 'Database Viewer',
    icon: '🗄',
    description: 'Interactive ERD canvas with Miro-style pan and zoom. Browse table schemas, preview rows, read column descriptions, and run arbitrary SQL queries.',
  },
]

const pages = [
  {
    name: 'Dashboard',
    group: 'Overview',
    description: 'Net worth overview with liquidity layers (cash, investments, home equity, retirement). Compensation split donut, net worth trend chart, upcoming RSU vests, and recent spending summary.',
  },
  {
    name: 'Spending',
    group: 'Money',
    description: 'Category breakdown with bar and donut charts, recurring expense detection, monthly spending trend, and full transaction search with filters.',
  },
  {
    name: 'Income',
    group: 'Money',
    description: 'W2 records by tax year. Salary vs RSU income breakdown, tax withholding waterfall (gross to net), year-over-year compensation table.',
  },
  {
    name: 'Cash',
    group: 'Money',
    description: 'Checking and savings balances, balance history chart, and notable transactions. Shows your most liquid money at a glance.',
  },
  {
    name: 'RSU',
    group: 'Investments',
    description: 'Grant details with vesting schedule, live stock price chart, tax lot analysis with short-term vs long-term gains, upcoming vest countdown, and "If You Sold Today" liquidation breakdown.',
  },
  {
    name: '401(k)',
    group: 'Investments',
    description: 'Balance breakdown by bucket (Roth, pre-tax, employer match). Contribution rates, individual holdings, and balance history chart.',
  },
  {
    name: 'Property',
    group: 'Property',
    description: 'Property value, mortgage balance, and equity position. Full amortization schedule chart with "Today" marker. Payment breakdown donut (principal, interest, escrow).',
  },
  {
    name: 'Assets',
    group: 'Property',
    description: 'Vehicle tracking with AI-estimated market values based on year, make, model, mileage, and condition. Depreciation tracking over time.',
  },
  {
    name: 'Planning',
    group: 'Planning',
    description: 'Retirement scenarios with year-by-year projections from now to your target retirement age. Assumption sliders for growth rates, returns, and spending. Sensitivity analysis shows which assumptions matter most.',
  },
  {
    name: 'Database',
    group: 'Platform',
    description: 'Interactive ERD canvas with Miro-style navigation. SQL runner for ad hoc queries. Table preview with row data, schema descriptions, and column-level documentation.',
  },
  {
    name: 'API',
    group: 'Platform',
    description: 'API key management (create, revoke, copy). Code examples for common operations. Link to the interactive Scalar-powered API reference at /developer.',
  },
  {
    name: 'Settings',
    group: 'Platform',
    description: 'Account management, income record editing, Plaid bank connections for automatic sync, and import history log.',
  },
  {
    name: 'Admin Portal',
    group: 'Platform',
    description: 'User management with role assignment, tenant management, and pending user approval queue. Admin-only access.',
  },
  {
    name: 'Guide',
    group: 'Overview',
    description: 'This page — a comprehensive feature tour and reference for how Tallied works.',
  },
]

const dataSources = [
  {
    name: 'Plaid',
    icon: '🔗',
    description: 'Automatic bank sync for transactions and balances. Connect in Settings, then sync on demand or let it run automatically.',
    feeds: 'Transactions, account balances',
  },
  {
    name: 'Document Import',
    icon: '📄',
    description: 'Upload W2s, pay stubs, 401(k) statements, or mortgage statements as PDFs. AI parses the document, you review the extracted data, and confirm to apply.',
    feeds: 'W2 records, mortgage data, 401(k) data',
  },
  {
    name: 'E-Trade',
    icon: '📊',
    description: 'RSU grant data via Excel spreadsheet upload. Export "Download by Type (expanded)" and "Download by Status (expanded)" from E-Trade.',
    feeds: 'RSU grants, vest events',
  },
  {
    name: 'Yahoo Finance',
    icon: '📈',
    description: 'Live stock prices fetched automatically and cached daily. Powers current holdings value and the stock price chart on the RSU page.',
    feeds: 'Stock prices',
  },
  {
    name: 'Manual Entry',
    icon: '✏️',
    description: 'Property valuations, vehicle details, and account configuration. Enter directly through the relevant page or Settings.',
    feeds: 'Property valuations, vehicles, accounts',
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
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-10">

    <!-- Header -->
    <div>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Tallied Guide</h1>
      <p class="mt-2 text-gray-500 dark:text-gray-400 text-sm">
        A comprehensive tour of features, pages, data sources, and platform capabilities.
      </p>
    </div>

    <!-- The Big Picture -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">The Big Picture</h2>
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6 text-sm text-gray-700 dark:text-gray-300 space-y-3 leading-relaxed">
        <p>
          <strong class="text-gray-900 dark:text-white">Tallied</strong> is a multi-tenant personal finance platform that tracks
          <strong class="text-gray-900 dark:text-white">net worth, income, spending, investments, property, and retirement planning</strong> in one place.
          It answers: are you on track to retire when you want to — and where does all your money actually go?
        </p>
        <p>
          The core loop is: <strong class="text-gray-900 dark:text-white">capture real data &rarr; understand your position &rarr; compare to your plan &rarr; adjust assumptions &rarr; repeat.</strong>
          Data flows in from Plaid (automatic bank sync), PDF/Excel uploads parsed by AI, Yahoo Finance (live stock prices), and manual entry.
          Every metric is transparent — hover over any tile to see the exact SQL query behind the number.
        </p>
      </div>
    </section>

    <!-- Navigation -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Navigation</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
        Pages are organized into six groups in the sidebar.
      </p>
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
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
        Capabilities that power the app beyond the financial dashboards.
      </p>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div v-for="feature in platformFeatures" :key="feature.name"
          class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="font-semibold text-gray-900 dark:text-white text-sm mb-1">{{ feature.icon }} {{ feature.name }}</div>
          <p class="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{{ feature.description }}</p>
        </div>
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
        </div>
      </div>
    </section>

    <!-- Pages -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Pages</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
        What each page shows and what it is for.
      </p>
      <div class="space-y-3">
        <div v-for="page in pages" :key="page.name"
          class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
          <button
            class="w-full text-left px-5 py-4 flex items-start gap-4"
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
          <div v-if="expandedSections[page.name]" class="px-5 pb-4 border-t border-gray-100 dark:border-gray-800">
            <p class="mt-3 text-sm text-gray-500 dark:text-gray-400 leading-relaxed">{{ page.description }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Data Sources -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">How Data Gets In</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
        Five sources feed data into Tallied.
      </p>
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

    <!-- Import Workflow -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Import Workflow</h2>
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6">
        <div class="grid grid-cols-1 sm:grid-cols-4 gap-4 text-center text-sm">
          <div>
            <div class="text-2xl mb-2">1. Upload</div>
            <p class="text-xs text-gray-500 dark:text-gray-400">Drop a PDF or Excel file into the import modal. Context-aware: it knows if you are on Income, Property, RSU, etc.</p>
          </div>
          <div>
            <div class="text-2xl mb-2">2. AI Parse</div>
            <p class="text-xs text-gray-500 dark:text-gray-400">Claude AI extracts structured data from the document and shows you what it found.</p>
          </div>
          <div>
            <div class="text-2xl mb-2">3. Review</div>
            <p class="text-xs text-gray-500 dark:text-gray-400">See the proposed changes before they are applied. Chat with AI to correct any mistakes.</p>
          </div>
          <div>
            <div class="text-2xl mb-2">4. Confirm</div>
            <p class="text-xs text-gray-500 dark:text-gray-400">Accept the changes and they are written to your database. Reject to discard.</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Getting Started -->
    <section>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Getting Started</h2>
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6 text-sm text-gray-700 dark:text-gray-300 space-y-2 leading-relaxed">
        <p><strong class="text-gray-900 dark:text-white">1.</strong> Sign in with Google. An admin will approve your account.</p>
        <p><strong class="text-gray-900 dark:text-white">2.</strong> Connect a bank via Plaid in Settings for automatic transaction and balance sync.</p>
        <p><strong class="text-gray-900 dark:text-white">3.</strong> Upload your W2s on the Income page to populate income history.</p>
        <p><strong class="text-gray-900 dark:text-white">4.</strong> Upload your mortgage statement on the Property page.</p>
        <p><strong class="text-gray-900 dark:text-white">5.</strong> Import RSU data from E-Trade on the RSU page.</p>
        <p><strong class="text-gray-900 dark:text-white">6.</strong> Add vehicles on the Assets page for AI-estimated values.</p>
        <p><strong class="text-gray-900 dark:text-white">7.</strong> Create a retirement plan on the Planning page and tune assumptions.</p>
        <p><strong class="text-gray-900 dark:text-white">8.</strong> Generate an API key on the API page if you want programmatic access.</p>
      </div>
    </section>

  </div>
</template>
