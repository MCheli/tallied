"""
Generate fake financial documents for test persona: Claudius Banks.

Creates realistic-looking PDFs that can be parsed by the AI import workflow.
These are committed to the repo for testing and demo purposes.
"""
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors

OUTPUT_DIR = Path(__file__).parent.parent / "fixtures" / "test_documents"

# ═══════════════════════════════════════════════════════════════════════════════
# CLAUDIUS BANKS — Test Persona
# ═══════════════════════════════════════════════════════════════════════════════

PERSONA = {
    "name": "CLAUDIUS BANKS",
    "address": "456 OAK STREET",
    "city_state_zip": "SPRINGFIELD MA 01101",
    "employer": "NEXUS TECHNOLOGIES",
    "employer_address": "200 INNOVATION DRIVE\nBOSTON, MA 02110",
    "ssn_last4": "7823",
    "ein": "04-3872156",
}

# Income data per year
INCOME = {
    2023: {
        "gross_pay": 185432.50, "base_salary": 130000.00, "rsu_income": 55432.50,
        "federal_tax": 32450.00, "state_tax": 8950.00, "social_security": 9932.40,
        "medicare": 2688.77, "pretax_401k": 8500.00, "roth_401k": 4500.00,
        "cafeteria_125": 2100.00, "transit": 780.00, "employer_health": 7800.00,
    },
    2024: {
        "gross_pay": 198750.00, "base_salary": 138000.00, "rsu_income": 60750.00,
        "federal_tax": 35200.00, "state_tax": 9800.00, "social_security": 10453.20,
        "medicare": 2881.88, "pretax_401k": 9200.00, "roth_401k": 4800.00,
        "cafeteria_125": 2200.00, "transit": 840.00, "employer_health": 8200.00,
    },
    2025: {
        "gross_pay": 210000.00, "base_salary": 145000.00, "rsu_income": 65000.00,
        "federal_tax": 38500.00, "state_tax": 10400.00, "social_security": 10918.20,
        "medicare": 3045.00, "pretax_401k": 10000.00, "roth_401k": 5000.00,
        "cafeteria_125": 2300.00, "transit": 900.00, "employer_health": 8600.00,
    },
}

MORTGAGE = {
    "account_number": "7845329100",
    "property_address": "456 Oak Street\nSpringfield, MA 01101",
    "original_amount": 380000.00,
    "current_balance": 362450.75,
    "rate": 4.25,
    "monthly_payment": 2450.00,
    "principal": 1102.40,
    "interest": 1283.43,
    "escrow": 64.17,
    "origination_date": "2021-06-15",
    "maturity_date": "06/2051",
    "escrow_balance": 3215.80,
}

RETIREMENT = {
    "plan_name": "NEXUS TECHNOLOGIES 401(K) PLAN",
    "provider": "Fidelity Investments",
    "total_balance": 185432.50,
    "vested_balance": 185432.50,
    "roth_balance": 129802.75,
    "pretax_balance": 18543.25,
    "employer_match_balance": 37086.50,
    "pretax_deferral_rate": 10,
    "roth_deferral_rate": 2,
    "roth_basis": 85000.00,
    "account_return_pct": 12.3,
    "employee_contributions_lifetime": 42000.00,
    "employer_contributions_lifetime": 12500.00,
    "estimated_monthly_income": 4520,
    "statement_start": "2025-10-01",
    "statement_end": "2025-12-31",
    "fund_name": "Fidelity Freedom 2055 Fund",
    "fund_ticker": "FDEEX",
    "fund_allocation": 100,
    "fund_gain_loss": 5432.50,
}

PAY_STUB = {
    "pay_date": "2025-12-19",
    "period_start": "12/07/2025",
    "period_end": "12/20/2025",
    "rate": 5576.92,  # biweekly
    "hours": 80,
    "ytd_regular": 145000.04,
    "ytd_rsu": 65000.00,
    "ytd_gross": 210000.00,
}


def _draw_header(c, title, subtitle=""):
    c.setFont("Helvetica-Bold", 16)
    c.drawString(1 * inch, 10.2 * inch, title)
    if subtitle:
        c.setFont("Helvetica", 10)
        c.drawString(1 * inch, 10.0 * inch, subtitle)


def _draw_field(c, x, y, label, value, bold_value=False):
    c.setFont("Helvetica", 9)
    c.drawString(x, y, label)
    c.setFont("Helvetica-Bold" if bold_value else "Helvetica", 9)
    c.drawRightString(x + 3.5 * inch, y, str(value))


def _fmt(n):
    return f"${n:,.2f}"


# ═══════════════════════════════════════════════════════════════════════════════
# W2 GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_w2(year: int):
    data = INCOME[year]
    filename = OUTPUT_DIR / f"{year} W2.pdf"
    c = canvas.Canvas(str(filename), pagesize=letter)

    _draw_header(c, f"Form W-2 Wage and Tax Statement — {year}")

    y = 9.5 * inch
    c.setFont("Helvetica", 9)

    # Employer info
    c.drawString(1 * inch, y, f"Employer: {PERSONA['employer']}")
    c.drawString(1 * inch, y - 15, f"EIN: {PERSONA['ein']}")
    y -= 40

    # Employee info
    c.drawString(1 * inch, y, f"Employee: {PERSONA['name']}")
    c.drawString(1 * inch, y - 15, f"Address: {PERSONA['address']}, {PERSONA['city_state_zip']}")
    c.drawString(1 * inch, y - 30, f"SSN: XXX-XX-{PERSONA['ssn_last4']}")
    y -= 60

    # Boxes
    c.setFont("Helvetica-Bold", 10)
    c.drawString(1 * inch, y, "Wage and Tax Data")
    y -= 20

    fields = [
        ("Gross Pay", _fmt(data["gross_pay"])),
        ("Box 1 - Wages, tips, other comp", _fmt(data["gross_pay"] - data["pretax_401k"] - data["cafeteria_125"] - data["transit"])),
        ("Box 2 - Federal income tax withheld", _fmt(data["federal_tax"])),
        ("Box 3 - Social security wages", _fmt(min(data["gross_pay"], 160200))),
        ("Box 4 - Social security tax withheld", _fmt(data["social_security"])),
        ("Box 5 - Medicare wages and tips", _fmt(data["gross_pay"])),
        ("Box 6 - Medicare tax withheld", _fmt(data["medicare"])),
        ("Box 12a - Code D (401k pretax)", _fmt(data["pretax_401k"])),
        ("Box 12b - Code AA (Roth 401k)", _fmt(data["roth_401k"])),
        ("Box 12c - Code DD (Employer health)", _fmt(data["employer_health"])),
        ("Box 17 - State income tax", _fmt(data["state_tax"])),
        ("Less Other Cafe 125", _fmt(data["cafeteria_125"])),
        ("Less Transportation-Salary Reduction", _fmt(data["transit"])),
    ]

    for label, value in fields:
        _draw_field(c, 1 * inch, y, label, value)
        y -= 16

    c.save()
    print(f"  Created: {filename.name}")


# ═══════════════════════════════════════════════════════════════════════════════
# MORTGAGE STATEMENT GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_mortgage_statement():
    m = MORTGAGE
    filename = OUTPUT_DIR / "mortgage-statement.pdf"
    c = canvas.Canvas(str(filename), pagesize=letter)

    _draw_header(c, "Mortgage Statement", "First National Bank")

    y = 9.5 * inch
    c.setFont("Helvetica", 10)
    c.drawString(1 * inch, y, f"Statement Date: 03/02/2026")
    c.drawString(4 * inch, y, f"Payment Due: 04/01/2026")
    y -= 30

    c.drawString(1 * inch, y, f"{PERSONA['name']}")
    c.drawString(1 * inch, y - 15, PERSONA['address'])
    c.drawString(1 * inch, y - 30, PERSONA['city_state_zip'])
    y -= 60

    c.setFont("Helvetica-Bold", 11)
    c.drawString(1 * inch, y, "Mortgage Information")
    y -= 20

    fields = [
        ("Account Number", m["account_number"]),
        ("Property Address", "456 Oak Street, Springfield, MA 01101"),
        ("Original Principal Balance", _fmt(m["original_amount"])),
        ("Unpaid Principal Balance", _fmt(m["current_balance"])),
        ("Interest Rate", f"{m['rate']:.5f}%"),
        ("Maturity Date", m["maturity_date"]),
        ("Escrow Balance", _fmt(m["escrow_balance"])),
    ]

    for label, value in fields:
        _draw_field(c, 1 * inch, y, label, value)
        y -= 16

    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1 * inch, y, "Explanation of Amount Due")
    y -= 20

    payment_fields = [
        ("Principal", _fmt(m["principal"])),
        ("Interest", _fmt(m["interest"])),
        ("Escrow", _fmt(m["escrow"])),
        ("Total Payment Due", _fmt(m["monthly_payment"])),
    ]

    for label, value in payment_fields:
        _draw_field(c, 1 * inch, y, label, value, bold_value=(label == "Total Payment Due"))
        y -= 16

    c.save()
    print(f"  Created: {filename.name}")


# ═══════════════════════════════════════════════════════════════════════════════
# 401(K) STATEMENT GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_retirement_statement():
    r = RETIREMENT
    filename = OUTPUT_DIR / "retirement-statement.pdf"
    c = canvas.Canvas(str(filename), pagesize=letter)

    _draw_header(c, f"{PERSONA['name']}", "Retirement Account Summary")

    y = 9.5 * inch
    c.setFont("Helvetica", 10)
    c.drawString(1 * inch, y, f"{r['plan_name']}")
    c.drawString(1 * inch, y - 15, f"c/o {r['provider']}")
    c.drawString(4 * inch, y, f"{r['statement_start']} to {r['statement_end']}")
    y -= 45

    c.setFont("Helvetica-Bold", 11)
    c.drawString(1 * inch, y, "Account at a Glance")
    y -= 20

    fields = [
        ("Ending Balance", _fmt(r["total_balance"])),
        ("Vested Balance", _fmt(r["vested_balance"])),
        ("Your Account Return", f"{r['account_return_pct']}%"),
        ("Estimated Monthly Income at Retirement", _fmt(r["estimated_monthly_income"])),
    ]

    for label, value in fields:
        _draw_field(c, 1 * inch, y, label, value, bold_value=True)
        y -= 16

    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1 * inch, y, "Activity by Contribution Type")
    y -= 20

    contrib_fields = [
        ("Roth Balance", _fmt(r["roth_balance"])),
        ("Salary Deferral (Pretax) Balance", _fmt(r["pretax_balance"])),
        ("Employer Match Balance", _fmt(r["employer_match_balance"])),
        ("Total Employee Contributions (since provider)", _fmt(r["employee_contributions_lifetime"])),
        ("Total Employer Contributions (since provider)", _fmt(r["employer_contributions_lifetime"])),
        ("Roth Basis", _fmt(r["roth_basis"])),
    ]

    for label, value in contrib_fields:
        _draw_field(c, 1 * inch, y, label, value)
        y -= 16

    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1 * inch, y, "Deferral Rates per Pay Period")
    y -= 20
    _draw_field(c, 1 * inch, y, "Salary Deferral", f"{r['pretax_deferral_rate']}%")
    y -= 16
    _draw_field(c, 1 * inch, y, "Roth Contributions", f"{r['roth_deferral_rate']}%")

    y -= 30
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1 * inch, y, "Investment Activity")
    y -= 20
    _draw_field(c, 1 * inch, y, f"{r['fund_name']} ({r['fund_ticker']})", _fmt(r["total_balance"]))
    y -= 16
    _draw_field(c, 1 * inch, y, "Future Allocation", f"{r['fund_allocation']}%")
    y -= 16
    _draw_field(c, 1 * inch, y, "Gain/Loss", _fmt(r["fund_gain_loss"]))

    c.save()
    print(f"  Created: {filename.name}")


# ═══════════════════════════════════════════════════════════════════════════════
# PAY STUB GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_pay_stub():
    p = PAY_STUB
    d = INCOME[2025]
    filename = OUTPUT_DIR / f"Pay Date {p['pay_date']}.pdf"
    c = canvas.Canvas(str(filename), pagesize=letter)

    _draw_header(c, "Earnings Statement", f"{PERSONA['employer']}")

    y = 9.5 * inch
    c.setFont("Helvetica", 9)
    c.drawString(1 * inch, y, f"Period: {p['period_start']} - {p['period_end']}")
    c.drawString(4 * inch, y, f"Pay Date: {p['pay_date']}")
    y -= 20
    c.drawString(1 * inch, y, PERSONA['name'])
    c.drawString(1 * inch, y - 12, f"{PERSONA['address']}, {PERSONA['city_state_zip']}")
    y -= 40

    c.setFont("Helvetica-Bold", 10)
    c.drawString(1 * inch, y, "Earnings")
    c.drawString(4.5 * inch, y, "Year to Date")
    y -= 18

    earnings = [
        ("Regular", f"{p['rate']:.2f}", _fmt(p['ytd_regular'])),
        ("RSU Gain", "", _fmt(p['ytd_rsu'])),
        ("Gross Pay", f"{p['rate']:.2f}", _fmt(p['ytd_gross'])),
    ]

    c.setFont("Helvetica", 9)
    for label, this_period, ytd in earnings:
        c.drawString(1 * inch, y, label)
        c.drawString(3 * inch, y, this_period)
        c.drawRightString(6 * inch, y, ytd)
        y -= 14

    y -= 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(1 * inch, y, "Deductions")
    c.drawString(4.5 * inch, y, "Year to Date")
    y -= 18

    deductions = [
        ("Federal Income Tax", _fmt(d["federal_tax"])),
        ("Medicare Tax", _fmt(d["medicare"])),
        ("MA State Income Tax", _fmt(d["state_tax"])),
        ("Social Security Tax", _fmt(d["social_security"])),
        ("401K Pre-Tax", _fmt(d["pretax_401k"])),
        ("401K Roth", _fmt(d["roth_401k"])),
        ("Dental + Medical", _fmt(d["cafeteria_125"])),
        ("Pretax Park", _fmt(d["transit"])),
    ]

    c.setFont("Helvetica", 9)
    for label, ytd in deductions:
        c.drawString(1 * inch, y, label)
        c.drawRightString(6 * inch, y, ytd)
        y -= 14

    c.save()
    print(f"  Created: {filename.name}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating Claudius Banks test documents...")
    print()

    for year in [2023, 2024, 2025]:
        generate_w2(year)

    generate_mortgage_statement()
    generate_retirement_statement()
    generate_pay_stub()

    print()
    print(f"All documents saved to: {OUTPUT_DIR}")
