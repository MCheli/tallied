# Test Document Manifest

All documents use the **Claudius Banks** test persona:
- Name: CLAUDIUS BANKS
- Employer: MICROSOFT CORPORATION
- Address: 456 Oak Street, Springfield, MA 01101
- SSN (masked): XXX-XX-7823

Values are consistent across related documents (W2 gross matches pay stub YTD, etc.)

---

## Income Documents

### `income/w2-standard-employer.pdf`
**Type:** W2 (2025) | **Context:** income | **Difficulty:** Standard

Full W2 with all boxes filled, official IRS-style layout with box grid.

| Expected Field | db_field | Value |
|---|---|---|
| Box 1 - Wages | w2_gross_pay (via w2_wages) | $197,700.00 |
| Box 2 - Federal tax | w2_federal_tax | $38,500.00 |
| Box 3 - SS wages | (informational) | $168,600.00 |
| Box 4 - SS tax | w2_social_security | $10,918.20 |
| Box 5 - Medicare wages | (informational - matches gross_pay) | $210,000.00 |
| Box 6 - Medicare tax | w2_medicare | $3,045.00 |
| Box 12a - Code D | w2_pretax_401k | $10,000.00 |
| Box 12b - Code AA | w2_roth_401k | $5,000.00 |
| Box 12c - Code DD | w2_employer_health | $8,600.00 |
| Box 14 - Transit | w2_transit | $900.00 |
| Box 17 - State tax | w2_state_tax | $10,400.00 |

**Note:** gross_pay ($210,000) = w2_wages ($197,700) + pretax_401k ($10,000) + cafeteria_125 ($2,300) + transit ($900). The AI should ideally compute gross_pay from Box 5 Medicare wages.

---

### `income/w2-minimal-fields.pdf`
**Type:** W2 (2024) | **Context:** income | **Difficulty:** Minimal

W2 with only essential boxes. No RSU breakdown, no cafeteria/transit, no Box 12.

| Expected Field | db_field | Value |
|---|---|---|
| Box 1 | w2_gross_pay (via wages) | $186,510.00 |
| Box 2 | w2_federal_tax | $35,200.00 |
| Box 4 | w2_social_security | $10,453.20 |
| Box 6 | w2_medicare | $2,881.88 |
| Box 17 | w2_state_tax | $9,800.00 |

**Missing fields (expected):** w2_base_salary, w2_rsu_income, w2_pretax_401k, w2_roth_401k, w2_cafeteria_125, w2_transit, w2_employer_health

---

### `income/w2-multiple-states.pdf`
**Type:** W2 (2025) | **Context:** income | **Difficulty:** Multi-state

W2 with income split across MA and CA. Two state tax entries.

| Expected Field | db_field | Value |
|---|---|---|
| Box 1 | w2_gross_pay | $197,700.00 |
| Box 2 | w2_federal_tax | $38,500.00 |
| Box 4 | w2_social_security | $10,918.20 |
| Box 6 | w2_medicare | $3,045.00 |
| Box 12a D | w2_pretax_401k | $10,000.00 |
| Box 12b AA | w2_roth_401k | $5,000.00 |
| Box 12c DD | w2_employer_health | $8,600.00 |
| Box 17 MA | w2_state_tax | $7,280.00 |
| Box 17 CA | w2_state_tax | $3,120.00 |

**Note:** State tax should sum both states: $7,280 + $3,120 = $10,400.00

---

### `income/w2-high-earner.pdf`
**Type:** W2 (2025) | **Context:** income | **Difficulty:** High income

$525K gross, $300K RSU. Tests handling of very high values and SS wage cap.

| Expected Field | db_field | Value |
|---|---|---|
| Box 1 | w2_gross_pay | $500,200.00 |
| Box 2 | w2_federal_tax | $142,500.00 |
| Box 4 | w2_social_security | $10,453.20 |
| Box 6 | w2_medicare | $7,612.50 |
| Box 12a D | w2_pretax_401k | $23,500.00 |
| Box 12c DD | w2_employer_health | $14,400.00 |
| Box 17 | w2_state_tax | $42,750.00 |

---

### `income/paystub-adp.pdf`
**Type:** Pay Stub (ADP format) | **Context:** income | **Difficulty:** Standard

ADP-branded bi-weekly pay stub with YTD totals in red-accented layout.

| Expected Field | db_field | Value (YTD) |
|---|---|---|
| Gross Pay | w2_gross_pay | $210,000.00 |
| Regular/Base | w2_base_salary | $145,000.00 |
| RSU Gain | w2_rsu_income | $65,000.00 |
| Federal Income Tax | w2_federal_tax | $38,500.00 |
| Social Security Tax | w2_social_security | $10,918.20 |
| Medicare Tax | w2_medicare | $3,045.00 |
| MA State Income Tax | w2_state_tax | $10,400.00 |
| 401(k) Pre-Tax | w2_pretax_401k | $10,000.00 |
| 401(k) Roth | w2_roth_401k | $5,000.00 |
| Dental + Medical (Sec 125) | w2_cafeteria_125 | $2,300.00 |
| Commuter/Transit | w2_transit | $900.00 |
| Employer Health (Box 12 DD) | w2_employer_health | $8,600.00 |

**Note:** AI should use YTD values, not per-period amounts.

---

### `income/paystub-workday.pdf`
**Type:** Pay Stub (Workday format) | **Context:** income | **Difficulty:** Modern layout

Workday-branded with colored summary boxes and categorized sections.

| Expected Field | db_field | Value (YTD) |
|---|---|---|
| Total Gross | w2_gross_pay | $210,000.00 |
| Base Salary | w2_base_salary | $145,000.00 |
| RSU Vesting Income | w2_rsu_income | $65,000.00 |
| Federal Income Tax | w2_federal_tax | $38,500.00 |
| Social Security | w2_social_security | $10,918.20 |
| Medicare | w2_medicare | $3,045.00 |
| MA State Income Tax | w2_state_tax | $10,400.00 |
| 401(k) Pre-Tax | w2_pretax_401k | $10,000.00 |
| 401(k) Roth | w2_roth_401k | $5,000.00 |
| Medical/Dental (Section 125) | w2_cafeteria_125 | $2,300.00 |
| Commuter Benefits | w2_transit | $900.00 |
| Employer Health Insurance | w2_employer_health | $8,600.00 |

---

## Retirement Documents

### `retirement/401k-fidelity-quarterly.pdf`
**Type:** 401(k) Statement (Fidelity) | **Context:** retirement | **Difficulty:** Full

Fidelity quarterly statement with 3 funds, Roth + pretax breakdown.

| Expected Field | db_field | Value |
|---|---|---|
| Plan Name | plan_name | MICROSOFT CORPORATION 401(K) PLAN |
| Provider | provider | Fidelity Investments |
| Total Balance | total_balance | $185,432.50 |
| Vested Balance | vested_balance | $185,432.50 |
| Roth Balance | roth_balance | $129,802.75 |
| Pre-Tax Balance | pretax_balance | $18,543.25 |
| Employer Match | employer_match_balance | $37,086.50 |
| Pre-Tax Deferral | pretax_deferral_rate_pct | 10% |
| Roth Deferral | roth_deferral_rate_pct | 2% |
| Employee Contributions | total_employee_contributions_lifetime | $42,000.00 |
| Employer Contributions | total_employer_contributions_lifetime | $12,500.00 |
| Roth Basis | roth_basis | $85,000.00 |
| Account Return | account_return_pct | 12.3% |
| Est. Monthly Income | estimated_monthly_income | $4,520.00 |
| Statement Start | statement_start | 2025-10-01 |
| Statement End | statement_end | 2025-12-31 |

**Holdings:**
| Fund | Ticker | Balance | Allocation | Gain/Loss |
|---|---|---|---|---|
| Fidelity Freedom 2055 Fund | FDEEX | $148,346.00 | 80% | $18,432.50 |
| Fidelity 500 Index Fund | FXAIX | $27,828.38 | 15% | $4,125.00 |
| Fidelity US Bond Index | FXNAX | $9,258.12 | 5% | -$312.50 |

---

### `retirement/401k-vanguard-annual.pdf`
**Type:** 401(k) Statement (Vanguard) | **Context:** retirement | **Difficulty:** Annual/Single fund

Vanguard annual statement. Single target-date fund. All balance fields present.

| Expected Field | db_field | Value |
|---|---|---|
| Total Balance | total_balance | $185,432.50 |
| Account Return | account_return_pct | 14.74% |
| Statement Period | statement_start / statement_end | 2025-01-01 to 2025-12-31 |

**Holdings:** Vanguard Target Retirement 2055 Fund (VFFVX), $185,432.50, 100%

(Same balance data as Fidelity -- provider and layout differ.)

---

### `retirement/401k-troweprice-quarterly.pdf`
**Type:** 401(k) Statement (T. Rowe Price) | **Context:** retirement | **Difficulty:** Full/4 funds

T. Rowe Price quarterly with 4 funds including stable value fund.

**Holdings:**
| Fund | Ticker | Balance | Allocation | Gain/Loss |
|---|---|---|---|---|
| T. Rowe Price Retirement 2055 Fund | TRRGX | $111,259.50 | 60% | $12,300.00 |
| T. Rowe Price Blue Chip Growth | TRBCX | $37,086.50 | 20% | $5,840.00 |
| T. Rowe Price Equity Index 500 | PREIX | $18,543.25 | 10% | $2,100.00 |
| T. Rowe Price Stable Value Fund | N/A | $18,543.25 | 10% | $430.00 |

---

### `retirement/401k-minimal.pdf`
**Type:** 401(k) Statement | **Context:** retirement | **Difficulty:** Minimal

Only total balance and one fund. No contribution rates, no Roth/pretax split.

| Expected Field | db_field | Value |
|---|---|---|
| Total Balance | total_balance | $185,432.50 |

**Missing fields (expected):** vested_balance, roth_balance, pretax_balance, employer_match_balance, pretax_deferral_rate_pct, roth_deferral_rate_pct

---

### `retirement/401k-with-loan.pdf`
**Type:** 401(k) Statement with Loan | **Context:** retirement | **Difficulty:** Edge case

Full Fidelity statement plus an outstanding 401(k) loan section.

| Expected Field | db_field | Value |
|---|---|---|
| Total Balance | total_balance | $185,432.50 |
| (all standard fields same as Fidelity) | ... | ... |
| Loan Balance | (not tracked in our DB) | $15,000.00 |
| Loan Rate | (not tracked) | 5.25% |

**Note:** The loan section is informational -- our DB does not track 401(k) loans.

---

## Property Documents

### `property/mortgage-chase.pdf`
**Type:** Mortgage Statement (Chase) | **Context:** property | **Difficulty:** Standard

Chase-branded monthly mortgage statement with recent activity.

| Expected Field | db_field | Value |
|---|---|---|
| Original Principal | mortgage_original_amount | $380,000.00 |
| Current Balance | mortgage_balance | $362,450.75 |
| Interest Rate | mortgage_rate | 4.25% |
| Monthly Payment | mortgage_monthly_payment | $2,450.00 |
| Escrow Balance | mortgage_escrow_balance | $3,215.80 |

---

### `property/mortgage-wells-fargo.pdf`
**Type:** Mortgage Statement (Wells Fargo) | **Context:** property | **Difficulty:** With escrow analysis

Wells Fargo statement with additional escrow analysis section (noise).

Same expected values as Chase (same underlying mortgage data).

---

### `property/mortgage-refi-statement.pdf`
**Type:** Closing Disclosure (Refinance) | **Context:** property | **Difficulty:** Edge case

Refinance closing disclosure with new loan terms. Different format from monthly statement.

| Expected Field | db_field | Value |
|---|---|---|
| Loan Amount | mortgage_original_amount | $355,000.00 |
| Interest Rate | mortgage_rate | 3.625% |
| Monthly P&I | mortgage_monthly_payment | $1,618.72 |
| Est. Total Monthly | (alt) mortgage_monthly_payment | $1,985.00 |

**Note:** This tests whether the AI handles a closing disclosure (not a monthly statement).

---

### `property/property-tax-bill.pdf`
**Type:** Property Tax Bill | **Context:** property | **Difficulty:** Non-mortgage

County property tax bill. Tests that the import system handles non-mortgage property documents gracefully.

| Expected Fields | Value |
|---|---|
| Assessed Value | $520,000.00 |
| Annual Tax | $5,850.00 |

**Note:** Our mortgage import does NOT track property tax bills. The AI should either extract no mortgage fields or note this is not a mortgage statement.

---

## RSU Documents

### `rsu/rsu-etrade-vesting.xlsx`
**Type:** E-Trade RSU Vesting Schedule | **Context:** rsu | **Difficulty:** Standard (native format)

Excel file matching E-Trade's export format with Grant/Vest Schedule/Tax Withholding row types.

**Grant 1:**
| Field | Value |
|---|---|
| grant_number | 094907 |
| symbol | MSFT |
| grant_date | 2023-05-15 |
| total_shares | 200 |
| vested_shares | 100 |
| unvested_shares | 100 |
| sellable_shares | 62 |
| share_price | $421.00 (84200/200) |

Vest events: 4 periods, 2 vested (periods 1-2), 2 pending (periods 3-4).

**Grant 2:**
| Field | Value |
|---|---|
| grant_number | 107234 |
| symbol | MSFT |
| grant_date | 2024-05-15 |
| total_shares | 250 |
| vested_shares | 0 |
| unvested_shares | 250 |

Vest events: 4 periods, all pending.

---

### `rsu/rsu-schwab-vesting.xlsx`
**Type:** Schwab RSU Report | **Context:** rsu | **Difficulty:** Different layout

Schwab's flat table format (all vest events in one table, no row-type column).
Same grant data as E-Trade but different column names and layout.

---

### `rsu/rsu-simple-grant-letter.pdf`
**Type:** RSU Grant Confirmation Letter | **Context:** rsu | **Difficulty:** Edge case

PDF letter (not a spreadsheet) confirming grant #107234.

| Field | Value |
|---|---|
| grant_number | 107234 |
| symbol | MSFT |
| grant_date | 2024-05-15 |
| total_shares | 250 |

**Note:** This is a letter, not a data export. Tests whether the AI can extract structured data from prose.
