# Planning v2: retirement outlook

Status: drafted and built 2026-10-29 on branch `worktree-agent-ab96287648ec64335`, then extended the same day with the owner's answers (birth date, access milestones and the early-retirement bridge, derived spending, withdrawal rules and nest egg, Social Security shortfall, acquisition and layoff scenarios, "sprint to retirement"). Ledger entries `PLAN-V2-*`. Supersedes the Planning paragraph's "year-by-year table" as the page's main experience; the table survives as one section.

## Why

The owner, October 2026: *"Currently planning is useless to me... The idea was that it would help me prepare for what retirement would look like with various options on how aggressively my income changes over time, what would happen depending on different spend rates during retirement, allow different macro economic scenarios to play out, etc. and then generate various visuals that would help me understand what would need to be true for that scenario to come to light and then also what that actually means for my wealth over time."*

What the page did before (verified in code, `PlanningView.vue` and `api/planning.py` at `a93de2d`):

- One deterministic projection, shown as a year x metric table. No chart of outcomes, no probabilities, no range.
- Plan rows fell to $0 income after the last scheduled RSU vest: `/plans/{id}/table` replaced RSU income with the vest schedule where one existed, and the engine's salary came from `W2Record.base_salary`, which a gross-only W-2 (the production shape) leaves empty.
- `current_age` defaulted to 30 and never advanced.
- One fixed rate of return per phase, one inflation, one spending rule, no life events, no macro scenarios, no goal-seek, no health care, no account-access rules.

## The jobs Planning must do for Mark

1. **J1 Will it work?** One number for the chance the money lasts, against a target he chose, and a second opinion from history.
2. **J2 What does it mean for my wealth over time?** The range of outcomes by age for investable assets and net worth, with the access milestones on the timeline; what the wealth is made of; what spending looks like in retirement.
3. **J3 What would need to be true?** For his target: the spending, retirement age, savings or returns that would get there, each on its own, under whichever macro scenario he picks.
4. **J4 Retirement age is a dimension.** Every plan comparable across retirement ages, with what opens at 55, 59½, 62, 65, full retirement age and 70, and a bridge model for the years before 59½.
5. **J5 What will retirement cost?** Spending derived from actual spending, with its uncertainty; what stops, continues or appears at retirement (mortgage, escrow, payroll tax, commuting, health insurance before and after 65, long-term care); reference points.
6. **J6 Withdrawal rules.** Fixed real, guardrails, VPW; spending shape (flat or smile); what nest egg each needs for 30–60-year horizons.
7. **J7 Income and career paths.** Flat / base / aggressive raises; an acquisition (cash-out at close, then different equity); a layoff (severance, benefit, accelerated vesting, a gap, then lower pay, no equity, or no job at all: "AI takes my job"); part-time bridge years.
8. **J8 Macro scenarios.** High inflation, stagflation, lost decade, depression, a crash in the first retired year, a strong market, low returns; Monte Carlo and every historical sequence.
9. **J9 Sprint to retirement.** Save as hard as possible now, retire at the earliest safe age, live lean: "to retire by X you need spending ≤ Y" and "at Y you retire at X", across return assumptions, with the levers that matter most.
10. **J10 Explain itself and keep plans.** Every chart says what it is and what feeds it; the page lists the real figures the plan starts from; levers are what-ifs until saved; any what-if can become a plan; plans compare side by side.

## How good planners present this (research)

| Idea | What it is | What Tallied takes from it |
|---|---|---|
| Monte Carlo "chance of success" | Simulate many return sequences; report the share where the money lasts (ProjectionLab, Boldin, adviser tools). | Headline number, 1,000 paths, fixed seed so a lever change is the only difference. |
| Fan chart | Percentile bands of wealth by age instead of one line. | 10–90% and 25–75% bands and the median, today's dollars, net-worth median overlaid, milestones marked. |
| "Probability of success" is a blunt label | Kitces: success/failure hides magnitude; dynamic spending turns failure into adjustment. | Under guardrails/VPW success also requires spending above a floor; spending bands and share of paths with a cut. |
| Sequence-of-returns risk | Bad returns early in retirement hurt most ("red zone"). | Replays anchored at the retirement year; a separate first-year-crash scenario. |
| Historical backtest (FIRECalc, cFIREsim) | Every historical start year; 1966 the classic worst. | Every complete sequence since 1928 (stocks, 10-year Treasuries, CPI); historical safe withdrawal rates by horizon, which match Early Retirement Now's published fail-safe rates to within 0.1 point. |
| 4% rule (Bengen 1994), Morningstar's annual study | Fixed real withdrawals; 4% survived every 30-year US period; Morningstar's 2026 base case 3.9% (30 years, 90%). | Fixed rule; nest-egg table with these as labelled references. |
| Longer horizons (Early Retirement Now SWR series) | 30/40/50/60-year fail-safe rates 3.82 / 3.58 / 3.35 / 3.25% (75/25). | Nest egg for 30–60 years and the plan's own horizon. |
| Guyton-Klinger guardrails | Skip raises after losing years; cut 10% at +20% withdrawal rate, raise 10% at −20%; 5.2–5.6% starting rates at 99% confidence. | Implemented with a sustainability gate (below). |
| VPW (Bogleheads) | Spend the annuity payment of the portfolio to the horizon. | Implemented; judged by the spending floor. |
| Retirement spending smile (Blanchett 2014) | Real spending falls about 1% a year, about 2% in the mid-70s, then rises late with health care. | "Smile" shape for living spending; health care modelled separately and rising faster than CPI. |
| Goal-seek, life events, scenario comparison (Boldin, ProjectionLab) | Max spending, earliest retirement, required savings; job loss, downsizing, early retirement. | Four goal-seeks per scenario; sprint grid; 14 event templates; per-event impact; plans side by side. |
| Account access before 59½ | Rule of 55; 72(t)/SEPP; Roth contribution basis. | Bridge model with each source drawn in the "how the early years are paid" chart. |

## Design options

### Option A: Outlook lab (recommended, built)

One page, two columns. Left: a sticky lever panel (spending rule and shape, retirement age, living spending, savings, comp growth with Flat/Base/Aggressive, retirement stock share, Social Security amount, claim age and the 2034 shortfall toggle, pay off the mortgage at retirement, 72(t); "All assumptions" for the rest). Right, top to bottom, each section titled as the question it answers: warnings; headline (chance of success, historical record, wealth at retirement, if it runs out / spending); starting point; wealth fan with milestones and scenario picker; retire at different ages; what would need to be true (cards, success-by-age and by-spending curves, the historical yardstick); what will retirement cost; what a retired year costs; how the early years are paid; what nest egg this needs; market scenarios; every historical start year; spending in retirement; what the wealth is made of; life events and career shocks with their outcomes; sprint to retirement; which levers matter most; year by year; plans side by side.

Levers run a what-if on the server (about 0.7 s for the full analysis); nothing is saved until **Save changes**; **Save as new plan** keeps a what-if. The sprint (about 3 s) runs once in the background per loaded plan and on request.

Trade-offs: dense, but every section answers one job and the levers are always in view.

### Option B: Guided questions

Question cards ("Can I retire at 55?", "What if I'm laid off at the acquisition?", "What if 1966 happens at 55?"), each with one chart and a sentence answer. Easier to read once, slower to explore: combining levers means walking through several cards.

### Option C: Scenario matrix

Plans as columns, outcomes as rows, small-multiple fans per plan. Best for comparing a few saved futures; weak at "what would need to be true", because each answer needs its own saved plan.

**Recommendation: A.** All of Mark's asks can be combined and moved at once; B's plain-language answers live in A's card text and C's comparison is A's last section.

## Scenario catalogue

Templates in `retirement_outlook.EVENT_TEMPLATES`; ages are filled relative to the current (c) or retirement (r) age, or fixed.

| Scenario | How it is modelled |
|---|---|
| Retire at 50 / 55 / 60 / 62 / 65 / 67 / 70 | Retirement-age table and curve under the selected scenario; each row says what opens |
| Employer acquired | At close: vested shares bought for cash at the deal price; unvested grants convert to cash at the deal price and pay on their original dates (taxed as pay); after close, equity replaced by a yearly amount (0 for none) |
| Layoff, back to work | Severance (weeks of pay), unemployment benefit up to 26 weeks (taxed), all unvested grants accelerate and pay at once (at the deal price after an acquisition), a gap with no pay (spending and COBRA/marketplace cover from savings), then a new job at a share of today's pay, with or without equity |
| Layoff, long gap and lower pay ("AI takes my job") | 18 months out, then 70% of pay and no equity |
| Layoff, never re-employed | Retires the plan at the layoff; optional part-time income to the planned retirement age; the outcome shows the minimum part-time income that keeps the plan line solvent, undoes the shock, or reaches the target |
| Part-time bridge years | Income (taxed at the pay rate) for an age range |
| Job loss (simple) | No pay for an age range |
| Company stock crash / boom | One-off price change |
| Big purchase, child costs, college | One-off or yearly costs |
| Long-term care | Three years from 85 at the assisted-living median |
| Relocation | Spending change from an age plus a moving cost |
| Downsizing | Sell (6% costs), pay off the mortgage, buy for cash; escrow scales with the new home |
| Windfall | One-off amount |
| Social Security timing and shortfall | Claim age 62–70; 81% payable from 2034 toggle |
| Income aggressiveness | Flat (inflation), Base (+1% real), Aggressive (+4% real) |
| Sprint to retirement | 401(k) at the IRS limit, every equity payout sold and invested; grid of max spending by retirement age × return (−2 to +1 points); earliest age by spending; tornado on spending, returns, pay after a job change, new equity, gap length |

## Macro scenarios

`retirement_sim.REGIMES`: your assumptions; strong market now (1982–1999 replay from today); crash in the first retired year (stocks −35%, bonds at their average); lost decade (2000–2009 from retirement); stagflation (1966–1981 from retirement); depression (1929–1941 from retirement); high inflation (+3 points for ten years, returns +1); low returns for good (−2 points). The selected scenario drives the wealth fan, the goal-seek, the retirement-age table, the sensitivity and the sprint. Every historical start year is shown separately.

## The maths

Engine: `backend/app/engine/retirement_sim.py` (numpy). Service: `backend/app/services/retirement_outlook.py`.

- **Time and age.** 12-month periods from today; age from the household birth date (`household_profile`), never typed. Money is nominal inside, reported in today's dollars by each path's price index.
- **Returns.** Lognormal around the plan's return per phase; volatility from the 1928–2025 record for the phase's stock share; company stock σ 30%, correlation 0.6; inflation AR(1) around the assumption. Plan line: every return at its median.
- **Income.** Comp grows at inflation + real raise; RSU share from today's split (`comp_split` for gross-only W-2s); scheduled vests at today's price × company price index; refresh grants ramp in over three years so income never drops to zero after the last known vest.
- **Spending in three parts.** Core living spending (rule and shape); housing (mortgage principal and interest until payoff, escrow for good, optional payoff at retirement); health care (marketplace before 65: benchmark per person, capped at 9.96% of last year's MAGI below 400% of the poverty line, full above it, MAGI floored at 138% FPL, full benchmark in the first retired year; Medicare-age costs from 65; both rise 2 points a year above CPI by default). MAGI = pre-tax 401(k) withdrawals + part-time pay + 85% of Social Security + half of taxable withdrawals (the gains share).
- **Bridge before 59½.** Cash, taxable and company stock first; then the Roth contribution basis (tax- and penalty-free); then the 401(k): without penalty if retirement is at 55 or later (rule of 55) or within the 72(t) amortization payment (5%, IRS single-life expectancy approximated as 86.2 − age); otherwise with the 10% penalty.
- **Social Security.** Monthly benefit at full retirement age (from the birth year) × the claiming factor (5/9% a month for 36 months early, 5/12% beyond, +8% a year to 70) × the payable share from 2034.
- **Spending rules.** Fixed; guardrails (Guyton-Klinger, gated: no cut and no skipped raise while the withdrawal rate is below the VPW rate for the remaining years, otherwise a 1% withdrawal rate is cut like a 6% one); VPW. Smile: about −1%/yr real early, −2%/yr in the mid-70s, back to −1% (approximation of Blanchett from published summaries; the exact regression could not be verified from the paper's text).
- **Success.** Every year's need covered to the plan-to age; under guardrails/VPW also spending ≥ floor × target.
- **Goal-seek and grids.** Bisection with common random numbers: max spending (rounded down), extra savings (rounded up), return shift, earliest age; sprint grid of max spending by age × return shift; minimum part-time income (plan line solvent / back to the no-shock chance / target).
- **Historical safe withdrawal rate.** For real returns g, the highest constant real withdrawal a sequence sustains is 1 / Σ_k Π_{j<k} 1/(1+g_j); worst and 10th percentile across complete sequences. Nest egg = first retired year's net need (living + housing + health − Social Security − part-time pay, grossed up for tax) / rate.
- **Spending builder.** Last 12 months of spending (D1 rules), one-off spikes (≥ $2,500, ≥ 10× the median purchase, in a category not bought most months), work costs (fuel, parking, tolls, transit) × the share that stops; range from the uncategorised amount to the trailing total.

Simplifications (stated on the page): one tax rate each for pay, RSUs and withdrawals (Roth basis tax-free); no RMDs or Roth conversion ladder; no correlation between inflation surprises and returns in Monte Carlo; the house pays nothing towards spending unless sold; vehicles not counted; capital gains on shares sold at an acquisition not taxed.

## Defaults and where they come from

| Default | Value | Source |
|---|---|---|
| Pre-65 benchmark premium per person | $15,000 | KFF: benchmark silver for a 60-year-old about $14,900 in 2026 after the enhanced credits expired |
| Premium cap below the cliff | 9.96% of MAGI | 2026 applicable percentage at the top of the scale; no subsidy above 400% FPL (enhanced credits ended Dec 31, 2025: AARP, KFF) |
| Poverty line | $15,650 + $5,500 per extra person | 2025 HHS guideline |
| Medicare-age health cost | $8,500 per person a year | Fidelity 2026 retiree estimate $185,500 for a 65-year-old (2025: $172,500) spread over about 22 years; Part B $202.90/month in 2026 |
| Health inflation above CPI | 2 points | Planning assumption (stated as such) |
| Long-term care template | $70,800 a year | Genworth/CareScout 2024 national median, assisted living (private nursing-home room $127,750) |
| Unemployment benefit | $1,105 a week, 26 weeks | Massachusetts maximum weekly benefit from Oct 5, 2025 (mass.gov) |
| Gap health cover | $9,500 a year | KFF 2025 average single premium $9,325; COBRA may charge up to 102% |
| Social Security shortfall | 81% from 2034 | 2025 Trustees Report (combined OASDI; OASI alone 77% from 2033) |
| 72(t) rate | 5% | IRS Notice 2022-6: up to the greater of 5% or 120% of the federal mid-term rate |
| Replacement ratio reference | 70–80% of pay | Common rule of thumb (Blanchett, summarised by Rob Berger) |
| BLS reference spending | 65+: $61,432; 65–74: $65,354 (2024); 75+: $53,031 (2023) | BLS Consumer Expenditure Survey via FRED |
| Safe withdrawal references | 4.0% (Bengen); 3.9% (Morningstar, 2026 retirees); 3.82/3.58/3.35/3.25% (ERN 30–60 years); 5.2–5.6% (Guyton-Klinger) | see sources |

## Sources

- Kitces, "Renaming the outcomes of a Monte Carlo retirement projection": https://www.kitces.com/blog/renaming-the-outcomes-of-a-monte-carlo-retirement-projection/
- Kitces, "Monte Carlo, guardrails, probability of adjustment": https://www.kitces.com/blog/monte-carlo-guardrails-probability-of-adjustment-success-client-communication-dynamic-retirement-spending/
- Kitces, "Implementing retirement income guardrails": https://www.kitces.com/blog/implementing-retirement-income-guardrails-to-facilitate-the-right-spending-raises-and-spending-cuts/
- Guyton and Klinger, "Decision Rules and Maximum Initial Withdrawal Rates", JFP 2006: https://www.financialplanningassociation.org/article/journal/MAR06-decision-rules-and-maximum-initial-withdrawal-rates
- Bogleheads/Finiki, "Variable percentage withdrawal": https://www.finiki.org/wiki/Variable_percentage_withdrawal
- Bengen 1994 summarised: https://firstmanhattan.com/uploads/images/Has-the-4-Rule-Stood-the-Test-of-Time.pdf
- Morningstar, safe withdrawal rate for 2026: https://www.morningstar.com/retirement/whats-safe-retirement-withdrawal-rate-2026 and https://www.morningstar.com.au/insights/personal-finance/258632/higher-valuations-lower-safe-withdrawal-rate-in-retirement
- Early Retirement Now, Safe Withdrawal Rate series: https://earlyretirementnow.com/safe-withdrawal-rate-series/ ; fail-safe table reproduced at https://choosefi.com/early-retirement-4-percent-rule
- Blanchett, "Exploring the Retirement Consumption Puzzle", JFP May 2014: https://www.financialplanningassociation.org/sites/default/files/2020-09/MAY14%20JFP%20Blanchett_0.pdf ; summaries: https://www.kitces.com/blog/estimating-changes-in-retirement-expenditures-and-the-retirement-spending-smile/ , https://retirementresearcher.com/retirement-spending-smile/ , https://robberger.com/research/estimating-the-true-cost-of-retirement/
- ProjectionLab Monte Carlo: https://projectionlab.com/monte-carlo ; Boldin scenarios: https://www.boldin.com/retirement/scenarios-to-try-with-a-comprehensive-retirement-calculator/
- Sequence risk "red zone": https://www.planadviser.com/beware-the-retirement-red-zone/
- Backtesting vs bootstrapping: https://thepoorswiss.com/backtesting-vs-bootstrapping-fire/
- 2025 Social Security Trustees Report: https://www.ssa.gov/OACT/TR/2025/II_E_conclu.html ; CBPP summary: https://www.cbpp.org/research/social-security/what-the-2025-trustees-report-shows-about-social-security
- Social Security claiming ages (Schwab): https://www.schwab.com/resource/socialsecurity
- Fidelity retiree health care estimate 2025 ($172,500): https://www.plansponsor.com/cost-for-health-care-in-retirement-hits-172500-per-fidelity-report/ ; 2026 ($185,500): https://www.planadviser.com/print-page?cid=121658
- Medicare Part B 2026 ($202.90): https://www.aarp.org/pri/topics/health/coverage-access/medicare-part-b-2026-premium-increase/
- KFF on expiring enhanced ACA credits and older enrollees: https://www.kff.org/quick-take/if-enhanced-aca-tax-credits-expire-older-marketplace-enrollees-face-steepest-premium-hikes/ ; subsidy cliff: https://www.healthinsurance.org/blog/marketplace-enrollees-face-return-of-the-subsidy-cliff/
- KFF 2025 Employer Health Benefits Survey: https://www.kff.org/health-costs/report/2025-employer-health-benefits-survey/
- Genworth/CareScout Cost of Care 2024: https://investor.genworth.com/news-events/press-releases/detail/982/
- IRS, substantially equal periodic payments: https://www.irs.gov/retirement-plans/substantially-equal-periodic-payments ; Notice 2022-6 (Groom): https://www.groom.com/wp-content/uploads/2022/12/n-22-06.pdf ; rule of 55 and 72(t): https://choosefi.com/tax-strategies/substantially-equal-periodic-payments-early-retirement
- Roth IRA ordering and five-year rules: https://www.kitces.com/blog/understanding-the-two-5-year-rules-for-roth-ira-contributions-and-conversions/
- Massachusetts unemployment benefit: https://www.mass.gov/service-details/understanding-your-base-period-and-benefit-year
- BLS Consumer Expenditure Survey by age (FRED): https://fred.stlouisfed.org/series/cxutotalexplb0407m , https://fred.stlouisfed.org/series/CXUTOTALEXPLB0408M ; BLS release: https://www.bls.gov/news.release/archives/cesan%5F12192025.htm
- Data: Damodaran (NYU Stern) annual returns 1928–2025: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histretSP.html ; BLS CPI-U (FRED CPIAUCNS): https://fred.stlouisfed.org/series/CPIAUCNS

## Data model changes

Migration `0005planv2` (iterates tenant schemas, runs on an empty database):

- `household_profile` (new): one row, `birth_date`.
- `plan_events` (new): `id, plan_id → plan_versions ON DELETE CASCADE, kind, label, start_age, end_age, amount, pct, enabled, params JSON, created_at`.
- `plan_versions.spending_rule` (fixed | guardrails | vpw) and `spending_profile` (flat | smile).
- `plan_assumptions`: existing plans gain the v2 keys at their defaults; existing values are untouched; `current_age` rows are removed (age comes from the birth date; downgrade puts them back at 30).
- `plan_projections` holds the new engine's plan line. Nothing is stored for a plan until the birth date is set.
- The vocabulary lives in `backend/app/services/plan_assumptions.py` with units, ranges and descriptions.

API (`/api/v1/plans`): `GET|PUT /household`, `GET /catalogue`, `GET /{id}/outlook?regime=&analysis=`, `POST /{id}/what-if` and `POST /{id}/sprint` (write nothing), `POST /{id}/events`, `PUT|DELETE /events/{event_id}`; `POST /` accepts `copy_from`, `spending_rule`, `spending_profile`; `PUT /{id}` upserts assumptions and both settings. Mutating routes require write permission. Without a birth date the outlook routes answer 422 and the page asks for it.

## Decisions only Mark can make

1. **Birth date** (entered once on the page; nothing is assumed).
2. **Target retirement age** and the **target chance of success** (default 85%).
3. **Retirement living spending**: start from the page's suggestion from actual spending, and choose fixed, guardrails or VPW, flat or smile, and the floor.
4. **Return assumptions.** The defaults (7% working, 5% retired, 3% inflation) are well below what the same mixes returned 1928–2025 (about 11% and 9% nominal). Conservative on purpose?
5. **Social Security** monthly estimate from ssa.gov/myaccount, claim age, and whether to plan on the 2034 shortfall.
6. **Health**: people insured, and whether the pre-65 premium and Medicare-age cost defaults fit.
7. **Acquisition terms**: close date, deal price vs today, and what equity replaces RSUs after close; **layoff terms**: severance weeks, gap, next pay, equity.
8. **RSU kept vs sold** at vest (default 50%), and whether vested company shares already sit in a brokerage account counted in net worth (to avoid counting them twice).
9. **Tax rates** on pay, RSUs and withdrawals.
