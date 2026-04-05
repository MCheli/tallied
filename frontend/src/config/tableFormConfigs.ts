import type { DataContext } from '../composables/useDataExplorer'
import { PAGE_TABLES } from '../composables/useDataExplorer'

export type FieldType = 'text' | 'number' | 'date' | 'select' | 'checkbox' | 'textarea'

export interface FieldConfig {
  name: string
  label: string
  type: FieldType
  description: string
  required?: boolean
  placeholder?: string
  options?: { value: string; label: string }[]
  /** decimal step for number inputs */
  step?: string
  /** true if this field should not appear in forms (auto-generated) */
  readOnly?: boolean
}

export interface TableFormConfig {
  table: string
  displayName: string
  description: string
  /** Primary key column name */
  pk: string
  /** Column shown in record list for identification */
  labelColumn: string
  /** Secondary column shown in record list */
  subtitleColumn?: string
  fields: FieldConfig[]
}

// ── W2 Records ───────────────────────────────────────────────────────────────

const w2RecordsConfig: TableFormConfig = {
  table: 'w2_records',
  displayName: 'W-2 Records',
  description: 'Annual W-2 wage and tax statements from your employer.',
  pk: 'id',
  labelColumn: 'tax_year',
  fields: [
    { name: 'tax_year', label: 'Tax Year', type: 'number', required: true,
      description: 'The calendar year this W-2 covers (e.g. 2024). Each year can only have one W-2 record.',
      placeholder: '2024' },
    { name: 'gross_pay', label: 'Gross Pay', type: 'number', step: '0.01',
      description: 'Total compensation before any deductions — includes base salary, RSU income, bonuses, and all other pay.' },
    { name: 'base_salary', label: 'Base Salary', type: 'number', step: '0.01',
      description: 'Your regular annual salary before bonuses, RSU, or other variable compensation.' },
    { name: 'rsu_income', label: 'RSU Income', type: 'number', step: '0.01',
      description: 'Income from Restricted Stock Unit (RSU) vesting events, reported as ordinary income on your W-2.' },
    { name: 'w2_wages', label: 'W-2 Wages (Box 1)', type: 'number', step: '0.01',
      description: 'Federal taxable wages from Box 1 of your W-2. This is gross pay minus pre-tax deductions (401k, health insurance, transit).' },
    { name: 'federal_tax', label: 'Federal Tax Withheld', type: 'number', step: '0.01',
      description: 'Total federal income tax withheld by your employer (Box 2).' },
    { name: 'state_tax', label: 'State Tax Withheld', type: 'number', step: '0.01',
      description: 'Total state income tax withheld (Box 17). Varies by state; some states have no income tax.' },
    { name: 'social_security', label: 'Social Security Tax', type: 'number', step: '0.01',
      description: 'Social Security tax withheld (Box 4). 6.2% of wages up to the annual wage base ($168,600 in 2024).' },
    { name: 'medicare', label: 'Medicare Tax', type: 'number', step: '0.01',
      description: 'Medicare tax withheld (Box 6). 1.45% of all wages, plus 0.9% additional tax on wages over $200K.' },
    { name: 'pretax_401k', label: 'Pre-Tax 401(k)', type: 'number', step: '0.01',
      description: 'Pre-tax 401(k) contributions (Box 12, code D). Reduces your taxable income but not Social Security/Medicare wages.' },
    { name: 'roth_401k', label: 'Roth 401(k)', type: 'number', step: '0.01',
      description: 'Roth 401(k) contributions (Box 12, code AA). Made with after-tax dollars; qualified withdrawals are tax-free in retirement.' },
    { name: 'cafeteria_125', label: 'Cafeteria Plan (Section 125)', type: 'number', step: '0.01',
      description: 'Pre-tax deductions for health/dental/vision insurance premiums under a Section 125 cafeteria plan.' },
    { name: 'transit', label: 'Transit Benefits', type: 'number', step: '0.01',
      description: 'Pre-tax transit/parking benefits (Box 12, code W). Up to $315/month for transit, $315/month for parking (2024).' },
    { name: 'employer_health', label: 'Employer Health Insurance', type: 'number', step: '0.01',
      description: 'Cost of employer-sponsored health coverage (Box 12, code DD). Informational only — not taxable income.' },
  ],
}

// ── RSU Grants ───────────────────────────────────────────────────────────────

const rsuGrantsConfig: TableFormConfig = {
  table: 'rsu_grants',
  displayName: 'RSU Grants',
  description: 'Restricted Stock Unit grants from your employer.',
  pk: 'id',
  labelColumn: 'company',
  subtitleColumn: 'grant_date',
  fields: [
    { name: 'company', label: 'Company', type: 'text', required: true,
      description: 'The company that issued this RSU grant (e.g. Microsoft, Apple).',
      placeholder: 'Microsoft' },
    { name: 'symbol', label: 'Ticker Symbol', type: 'text',
      description: 'Stock ticker symbol used for price lookups (e.g. MSFT, AAPL).',
      placeholder: 'MSFT' },
    { name: 'grant_date', label: 'Grant Date', type: 'date',
      description: 'The date the RSU grant was awarded. Vesting schedules are measured from this date.' },
    { name: 'total_shares', label: 'Total Shares', type: 'number',
      description: 'Total number of shares in this grant before any vesting.' },
    { name: 'vested_shares', label: 'Vested Shares', type: 'number',
      description: 'Number of shares that have already vested and been delivered to you.' },
    { name: 'unvested_shares', label: 'Unvested Shares', type: 'number',
      description: 'Number of shares still on the vesting schedule — you forfeit these if you leave the company.' },
    { name: 'sellable_shares', label: 'Sellable Shares', type: 'number',
      description: 'Shares you currently hold and can sell. May differ from vested shares if some were sold for taxes at vest.' },
    { name: 'share_price', label: 'Share Price at Grant', type: 'number', step: '0.01',
      description: 'The stock price on the grant date. Used to calculate the original grant value.' },
  ],
}

// ── Vest Events ──────────────────────────────────────────────────────────────

const vestEventsConfig: TableFormConfig = {
  table: 'vest_events',
  displayName: 'Vest Events',
  description: 'Individual RSU vesting events when shares are released to you.',
  pk: 'id',
  labelColumn: 'vest_date',
  subtitleColumn: 'shares',
  fields: [
    { name: 'grant_id', label: 'Grant ID', type: 'text', required: true,
      description: 'The RSU grant this vest event belongs to. Links to the rsu_grants table.' },
    { name: 'vest_date', label: 'Vest Date', type: 'date', required: true,
      description: 'The date these shares vested (were released to you).' },
    { name: 'vest_period', label: 'Vest Period', type: 'number',
      description: 'Which vesting period this is (1st, 2nd, 3rd, etc.). Helps track position in the vesting schedule.' },
    { name: 'shares', label: 'Gross Shares', type: 'number', required: true,
      description: 'Total number of shares vesting in this event, before tax withholding.' },
    { name: 'fmv_at_vest', label: 'Fair Market Value', type: 'number', step: '0.01',
      description: 'Stock price on the vest date. This becomes your cost basis for capital gains calculations.' },
    { name: 'shares_withheld', label: 'Shares Withheld', type: 'number',
      description: 'Shares sold automatically to cover federal, state, and FICA taxes. Typically ~35-40% of gross shares.' },
    { name: 'shares_released', label: 'Net Shares Released', type: 'number',
      description: 'Shares actually deposited into your brokerage account after tax withholding (gross - withheld).' },
    { name: 'total_taxes_paid', label: 'Total Taxes Paid', type: 'number', step: '0.01',
      description: 'Dollar amount of taxes paid via share withholding (shares_withheld x FMV).' },
    { name: 'is_actual', label: 'Already Vested', type: 'checkbox',
      description: 'Check if this vest has already occurred. Uncheck for future projected vests.' },
  ],
}

// ── Stock Prices ─────────────────────────────────────────────────────────────

const stockPricesConfig: TableFormConfig = {
  table: 'stock_prices',
  displayName: 'Stock Prices',
  description: 'Historical stock price data used for RSU valuations.',
  pk: 'id',
  labelColumn: 'symbol',
  subtitleColumn: 'price_date',
  fields: [
    { name: 'symbol', label: 'Ticker Symbol', type: 'text', required: true,
      description: 'Stock ticker symbol (e.g. MSFT, AAPL).',
      placeholder: 'MSFT' },
    { name: 'price_date', label: 'Price Date', type: 'date', required: true,
      description: 'The trading date for this price record.' },
    { name: 'close_price', label: 'Closing Price', type: 'number', step: '0.01', required: true,
      description: 'The stock closing price on this date.' },
    { name: 'source', label: 'Source', type: 'text',
      description: 'Where this price came from (e.g. yahoo, manual, api).',
      placeholder: 'yahoo' },
  ],
}

// ── Retirement Account ───────────────────────────────────────────────────────

const retirementAccountsConfig: TableFormConfig = {
  table: 'retirement_accounts',
  displayName: 'Retirement Accounts',
  description: 'Your 401(k) or other employer-sponsored retirement accounts.',
  pk: 'id',
  labelColumn: 'plan_name',
  subtitleColumn: 'provider',
  fields: [
    { name: 'plan_name', label: 'Plan Name', type: 'text', required: true,
      description: 'The name of your retirement plan (e.g. "Microsoft 401(k)").',
      placeholder: 'Company 401(k)' },
    { name: 'provider', label: 'Provider', type: 'text',
      description: 'The financial institution managing the plan (e.g. Fidelity, Vanguard, Schwab).',
      placeholder: 'Fidelity' },
    { name: 'total_balance', label: 'Total Balance', type: 'number', step: '0.01',
      description: 'Current total account balance across all contribution types.' },
    { name: 'vested_balance', label: 'Vested Balance', type: 'number', step: '0.01',
      description: 'Amount you are entitled to if you leave the company. May be less than total if employer match has a vesting schedule.' },
    { name: 'roth_balance', label: 'Roth Balance', type: 'number', step: '0.01',
      description: 'Balance from Roth (after-tax) contributions. Qualified withdrawals in retirement are tax-free.' },
    { name: 'pretax_balance', label: 'Pre-Tax Balance', type: 'number', step: '0.01',
      description: 'Balance from traditional pre-tax contributions. Withdrawals in retirement are taxed as ordinary income.' },
    { name: 'employer_match_balance', label: 'Employer Match Balance', type: 'number', step: '0.01',
      description: 'Balance from your employer\'s matching contributions. Always pre-tax, even if your contributions are Roth.' },
    { name: 'pretax_deferral_rate', label: 'Pre-Tax Deferral Rate', type: 'number', step: '0.001',
      description: 'Your pre-tax contribution rate as a decimal (e.g. 0.08 = 8% of salary).',
      placeholder: '0.08' },
    { name: 'roth_deferral_rate', label: 'Roth Deferral Rate', type: 'number', step: '0.001',
      description: 'Your Roth contribution rate as a decimal (e.g. 0.05 = 5% of salary).',
      placeholder: '0.05' },
    { name: 'total_employee_contributions', label: 'Lifetime Employee Contributions', type: 'number', step: '0.01',
      description: 'Total amount you have contributed over the life of the account.' },
    { name: 'total_employer_contributions', label: 'Lifetime Employer Contributions', type: 'number', step: '0.01',
      description: 'Total employer match/contributions over the life of the account.' },
    { name: 'account_return', label: 'Account Return', type: 'number', step: '0.0001',
      description: 'Investment return as a decimal (e.g. 0.12 = 12% return). Period defined by return_period_start.' },
    { name: 'return_period_start', label: 'Return Period Start', type: 'date',
      description: 'Start date for the account return calculation (e.g. beginning of year for YTD return).' },
    { name: 'statement_start', label: 'Statement Start', type: 'date',
      description: 'Start date of the most recent statement period.' },
    { name: 'statement_end', label: 'Statement End', type: 'date',
      description: 'End date of the most recent statement period.' },
  ],
}

// ── Retirement Holdings ──────────────────────────────────────────────────────

const retirementHoldingsConfig: TableFormConfig = {
  table: 'retirement_holdings',
  displayName: 'Retirement Holdings',
  description: 'Individual fund holdings within your retirement account.',
  pk: 'id',
  labelColumn: 'fund_name',
  subtitleColumn: 'ticker',
  fields: [
    { name: 'retirement_account_id', label: 'Retirement Account ID', type: 'number', required: true,
      description: 'The retirement account this holding belongs to.' },
    { name: 'fund_name', label: 'Fund Name', type: 'text', required: true,
      description: 'Full name of the mutual fund or investment (e.g. "T. Rowe Price Retirement 2060").',
      placeholder: 'Vanguard Target Retirement 2060' },
    { name: 'ticker', label: 'Ticker', type: 'text',
      description: 'Fund ticker symbol if available (e.g. TRRGX, VTTSX).',
      placeholder: 'VTTSX' },
    { name: 'balance', label: 'Balance', type: 'number', step: '0.01',
      description: 'Current dollar value of this holding.' },
    { name: 'allocation_pct', label: 'Allocation %', type: 'number', step: '0.01',
      description: 'What percentage of your total retirement portfolio this fund represents (e.g. 45.5 for 45.5%).' },
    { name: 'gain_loss', label: 'Gain/Loss', type: 'number', step: '0.01',
      description: 'Unrealized gain or loss on this holding. Positive = gain, negative = loss.' },
  ],
}

// ── Retirement Snapshots ─────────────────────────────────────────────────────

const retirementSnapshotsConfig: TableFormConfig = {
  table: 'retirement_snapshots',
  displayName: 'Retirement Snapshots',
  description: 'Point-in-time balance snapshots for tracking retirement account growth over time.',
  pk: 'id',
  labelColumn: 'snapshot_date',
  subtitleColumn: 'balance',
  fields: [
    { name: 'retirement_account_id', label: 'Retirement Account ID', type: 'number', required: true,
      description: 'The retirement account this snapshot records.' },
    { name: 'snapshot_date', label: 'Snapshot Date', type: 'date', required: true,
      description: 'The date this balance was recorded.' },
    { name: 'balance', label: 'Total Balance', type: 'number', step: '0.01', required: true,
      description: 'Total account balance on this date.' },
    { name: 'roth_balance', label: 'Roth Balance', type: 'number', step: '0.01',
      description: 'Roth portion of the balance on this date.' },
    { name: 'pretax_balance', label: 'Pre-Tax Balance', type: 'number', step: '0.01',
      description: 'Pre-tax (traditional) portion of the balance.' },
    { name: 'employer_balance', label: 'Employer Balance', type: 'number', step: '0.01',
      description: 'Employer match portion of the balance.' },
    { name: 'source', label: 'Source', type: 'select',
      description: 'How this snapshot was captured.',
      options: [
        { value: 'statement', label: 'Statement' },
        { value: 'manual', label: 'Manual Entry' },
      ] },
  ],
}

// ── Mortgages ────────────────────────────────────────────────────────────────

const mortgagesConfig: TableFormConfig = {
  table: 'mortgages',
  displayName: 'Mortgages',
  description: 'Mortgage loan details for your properties.',
  pk: 'id',
  labelColumn: 'property_address',
  subtitleColumn: 'current_balance',
  fields: [
    { name: 'account_id', label: 'Account ID', type: 'text', required: true,
      description: 'The linked account in Tallied that tracks this mortgage.' },
    { name: 'property_address', label: 'Property Address', type: 'text',
      description: 'Full address of the mortgaged property.',
      placeholder: '123 Main St, Springfield, MA' },
    { name: 'rate', label: 'Interest Rate', type: 'number', step: '0.001', required: true,
      description: 'Annual interest rate as a decimal (e.g. 0.0425 for 4.25%). Not a percentage.',
      placeholder: '0.0425' },
    { name: 'monthly_payment', label: 'Monthly Payment', type: 'number', step: '0.01', required: true,
      description: 'Total monthly mortgage payment including principal, interest, and escrow.' },
    { name: 'origination_date', label: 'Origination Date', type: 'date',
      description: 'The date the mortgage was originated (loan closing date).' },
    { name: 'original_amount', label: 'Original Loan Amount', type: 'number', step: '0.01',
      description: 'The initial loan amount at origination.' },
    { name: 'original_payoff_date', label: 'Original Payoff Date', type: 'date',
      description: 'The scheduled final payment date based on the original loan term (e.g. 30 years from origination).' },
    { name: 'current_balance', label: 'Current Balance', type: 'number', step: '0.01',
      description: 'Outstanding principal balance on the mortgage.' },
    { name: 'escrow', label: 'Monthly Escrow', type: 'number', step: '0.01',
      description: 'Monthly escrow amount for property taxes and homeowners insurance, included in your payment.' },
  ],
}

// ── Property Valuations ──────────────────────────────────────────────────────

const propertyValuationsConfig: TableFormConfig = {
  table: 'property_valuations',
  displayName: 'Property Valuations',
  description: 'Estimated property values from various sources.',
  pk: 'id',
  labelColumn: 'valuation_date',
  subtitleColumn: 'value',
  fields: [
    { name: 'account_id', label: 'Account ID', type: 'text', required: true,
      description: 'The property account this valuation is linked to.' },
    { name: 'valuation_date', label: 'Valuation Date', type: 'date', required: true,
      description: 'The date this valuation was assessed or estimated.' },
    { name: 'value', label: 'Estimated Value', type: 'number', step: '0.01', required: true,
      description: 'The estimated market value of the property in dollars.' },
    { name: 'source', label: 'Source', type: 'select',
      description: 'Where this valuation came from.',
      options: [
        { value: 'zillow', label: 'Zillow' },
        { value: 'redfin', label: 'Redfin' },
        { value: 'tax_assessment', label: 'Tax Assessment' },
        { value: 'appraisal', label: 'Professional Appraisal' },
        { value: 'manual', label: 'Manual Estimate' },
      ] },
  ],
}

// ── Property Value Histories ─────────────────────────────────────────────────

const propertyValueHistoriesConfig: TableFormConfig = {
  table: 'property_value_histories',
  displayName: 'Property Value History',
  description: 'Historical property value records for tracking appreciation over time.',
  pk: 'id',
  labelColumn: 'date',
  subtitleColumn: 'value',
  fields: [
    { name: 'account_id', label: 'Account ID', type: 'text', required: true,
      description: 'The property account this history entry belongs to.' },
    { name: 'date', label: 'Date', type: 'date', required: true,
      description: 'The date of this value record.' },
    { name: 'value', label: 'Value', type: 'number', step: '0.01', required: true,
      description: 'The property value on this date.' },
    { name: 'source', label: 'Source', type: 'select', required: true,
      description: 'The source or type of this valuation.',
      options: [
        { value: 'tax_assessment', label: 'Tax Assessment' },
        { value: 'realtor_estimate', label: 'Realtor Estimate' },
        { value: 'sale', label: 'Sale Price' },
        { value: 'ai_projection', label: 'AI Projection' },
        { value: 'manual', label: 'Manual' },
      ] },
    { name: 'is_projected', label: 'Projected', type: 'checkbox',
      description: 'Check if this is a projected/estimated future value rather than an actual recorded value.' },
  ],
}

// ── Vehicles ─────────────────────────────────────────────────────────────────

const vehiclesConfig: TableFormConfig = {
  table: 'vehicles',
  displayName: 'Vehicles',
  description: 'Your vehicles and their current values.',
  pk: 'id',
  labelColumn: 'make',
  subtitleColumn: 'model',
  fields: [
    { name: 'year', label: 'Year', type: 'number', required: true,
      description: 'Model year of the vehicle.',
      placeholder: '2024' },
    { name: 'make', label: 'Make', type: 'text', required: true,
      description: 'Vehicle manufacturer (e.g. Toyota, Honda, Tesla).',
      placeholder: 'Toyota' },
    { name: 'model', label: 'Model', type: 'text', required: true,
      description: 'Vehicle model name (e.g. RAV4, Civic, Model 3).',
      placeholder: 'RAV4' },
    { name: 'trim', label: 'Trim', type: 'text',
      description: 'Specific trim level if applicable (e.g. XLE, Sport, Long Range).',
      placeholder: 'XLE Premium' },
    { name: 'vin', label: 'VIN', type: 'text',
      description: 'Vehicle Identification Number — 17-character unique identifier found on your registration or dashboard.',
      placeholder: '1HGBH41JXMN109186' },
    { name: 'mileage', label: 'Current Mileage', type: 'number',
      description: 'Current odometer reading. Higher mileage typically reduces trade-in and private party value.' },
    { name: 'condition', label: 'Condition', type: 'select',
      description: 'Overall vehicle condition using standard KBB/NADA grades.',
      options: [
        { value: 'excellent', label: 'Excellent' },
        { value: 'very_good', label: 'Very Good' },
        { value: 'good', label: 'Good' },
        { value: 'fair', label: 'Fair' },
        { value: 'poor', label: 'Poor' },
      ] },
    { name: 'purchase_price', label: 'Purchase Price', type: 'number', step: '0.01',
      description: 'What you paid for the vehicle (including tax/fees if desired). Used to track depreciation.' },
    { name: 'purchase_date', label: 'Purchase Date', type: 'date',
      description: 'When you bought the vehicle.' },
    { name: 'estimated_value', label: 'Estimated Value', type: 'number', step: '0.01',
      description: 'Current estimated market value. Updated automatically by AI valuation or manually.' },
    { name: 'notes', label: 'Notes', type: 'textarea',
      description: 'Any additional notes about the vehicle.' },
  ],
}

// ── Asset Value Histories ────────────────────────────────────────────────────

const assetValueHistoriesConfig: TableFormConfig = {
  table: 'asset_value_histories',
  displayName: 'Asset Value History',
  description: 'Historical value records for vehicles and other assets.',
  pk: 'id',
  labelColumn: 'date',
  subtitleColumn: 'value',
  fields: [
    { name: 'vehicle_id', label: 'Vehicle ID', type: 'number', required: true,
      description: 'The vehicle this value record belongs to.' },
    { name: 'date', label: 'Date', type: 'date', required: true,
      description: 'The date of this value estimate.' },
    { name: 'value', label: 'Value', type: 'number', step: '0.01', required: true,
      description: 'Estimated vehicle value on this date.' },
    { name: 'source', label: 'Source', type: 'select', required: true,
      description: 'How this value was determined.',
      options: [
        { value: 'ai_estimate', label: 'AI Estimate' },
        { value: 'purchase', label: 'Purchase Price' },
        { value: 'manual', label: 'Manual Entry' },
      ] },
    { name: 'is_projected', label: 'Projected', type: 'checkbox',
      description: 'Check if this is a projected future value rather than a recorded actual.' },
  ],
}

// ── Accounts ─────────────────────────────────────────────────────────────────

const accountsConfig: TableFormConfig = {
  table: 'accounts',
  displayName: 'Accounts',
  description: 'Financial accounts — checking, savings, credit cards, loans, investment accounts.',
  pk: 'id',
  labelColumn: 'name',
  subtitleColumn: 'institution',
  fields: [
    { name: 'name', label: 'Account Name', type: 'text', required: true,
      description: 'A descriptive name for this account (e.g. "Chase Checking", "Fidelity 401k").',
      placeholder: 'Chase Checking' },
    { name: 'institution', label: 'Institution', type: 'text',
      description: 'The bank or financial institution (e.g. Chase, Fidelity, Vanguard).',
      placeholder: 'Chase' },
    { name: 'account_type', label: 'Account Type', type: 'select', required: true,
      description: 'The type of financial account.',
      options: [
        { value: 'checking', label: 'Checking' },
        { value: 'savings', label: 'Savings' },
        { value: 'credit_card', label: 'Credit Card' },
        { value: 'mortgage', label: 'Mortgage' },
        { value: 'investment', label: 'Investment' },
        { value: 'retirement', label: 'Retirement' },
        { value: 'loan', label: 'Loan' },
        { value: 'property', label: 'Property' },
        { value: 'other', label: 'Other' },
      ] },
    { name: 'display_group', label: 'Display Group', type: 'select', required: true,
      description: 'How this account is grouped in the dashboard. Controls where it appears in net worth calculations.',
      options: [
        { value: 'cash', label: 'Cash' },
        { value: 'investments', label: 'Investments' },
        { value: 'property', label: 'Property' },
        { value: 'debt', label: 'Debt' },
        { value: 'retirement', label: 'Retirement' },
        { value: 'other', label: 'Other' },
      ] },
    { name: 'include_in_nw', label: 'Include in Net Worth', type: 'checkbox',
      description: 'Whether this account\'s balance counts toward your net worth calculation. Uncheck for tracking-only accounts.' },
    { name: 'notes', label: 'Notes', type: 'textarea',
      description: 'Any additional notes about this account.' },
  ],
}

// ── Transactions ─────────────────────────────────────────────────────────────

const transactionsConfig: TableFormConfig = {
  table: 'transactions',
  displayName: 'Transactions',
  description: 'Individual financial transactions — purchases, deposits, transfers.',
  pk: 'id',
  labelColumn: 'merchant',
  subtitleColumn: 'amount',
  fields: [
    { name: 'account_id', label: 'Account ID', type: 'text',
      description: 'The account this transaction belongs to.' },
    { name: 'date', label: 'Date', type: 'date', required: true,
      description: 'The date the transaction occurred.' },
    { name: 'amount', label: 'Amount', type: 'number', step: '0.01', required: true,
      description: 'Transaction amount. Negative for expenses/debits, positive for income/credits.',
      placeholder: '-45.99' },
    { name: 'merchant', label: 'Merchant', type: 'text',
      description: 'The merchant or payee name.',
      placeholder: 'Whole Foods' },
    { name: 'category', label: 'Category', type: 'text',
      description: 'Spending category (e.g. Groceries, Restaurants, Gas, Utilities).',
      placeholder: 'Groceries' },
    { name: 'category_group', label: 'Category Group', type: 'text',
      description: 'Broader category group (e.g. Food & Drink, Transportation, Housing).',
      placeholder: 'Food & Drink' },
    { name: 'is_recurring', label: 'Recurring', type: 'checkbox',
      description: 'Check if this is a recurring transaction (subscription, utility bill, etc.).' },
    { name: 'notes', label: 'Notes', type: 'textarea',
      description: 'Any additional notes about this transaction.' },
    { name: 'source', label: 'Source', type: 'text',
      description: 'Where this transaction was imported from (e.g. monarch, plaid, manual).',
      placeholder: 'manual' },
  ],
}

// ── Balance Snapshots ────────────────────────────────────────────────────────

const balanceSnapshotsConfig: TableFormConfig = {
  table: 'balance_snapshots',
  displayName: 'Balance Snapshots',
  description: 'Point-in-time account balance records for tracking balances over time.',
  pk: 'id',
  labelColumn: 'snapshot_date',
  subtitleColumn: 'balance',
  fields: [
    { name: 'account_id', label: 'Account ID', type: 'text', required: true,
      description: 'The account this balance snapshot belongs to.' },
    { name: 'snapshot_date', label: 'Snapshot Date', type: 'date', required: true,
      description: 'The date this balance was recorded.' },
    { name: 'balance', label: 'Balance', type: 'number', step: '0.01',
      description: 'The account balance on this date.' },
    { name: 'source', label: 'Source', type: 'text',
      description: 'Where this balance came from (e.g. plaid, manual, monarch).',
      placeholder: 'manual' },
  ],
}

// ── Config registry ──────────────────────────────────────────────────────────

const ALL_CONFIGS: Record<string, TableFormConfig> = {
  w2_records: w2RecordsConfig,
  rsu_grants: rsuGrantsConfig,
  vest_events: vestEventsConfig,
  stock_prices: stockPricesConfig,
  retirement_accounts: retirementAccountsConfig,
  retirement_holdings: retirementHoldingsConfig,
  retirement_snapshots: retirementSnapshotsConfig,
  mortgages: mortgagesConfig,
  property_valuations: propertyValuationsConfig,
  property_value_histories: propertyValueHistoriesConfig,
  vehicles: vehiclesConfig,
  asset_value_histories: assetValueHistoriesConfig,
  accounts: accountsConfig,
  transactions: transactionsConfig,
  balance_snapshots: balanceSnapshotsConfig,
}

/** Get form configs for a given page context */
export function getFormConfigs(context: DataContext): TableFormConfig[] {
  const tables = PAGE_TABLES[context] ?? []
  return tables.map(t => ALL_CONFIGS[t]).filter(Boolean)
}

/** Get a single table's form config */
export function getFormConfig(tableName: string): TableFormConfig | undefined {
  return ALL_CONFIGS[tableName]
}
