"""Pydantic schemas for everything Claude is asked to produce (structured outputs)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]

W2_DB_FIELDS = (
    "w2_gross_pay", "w2_base_salary", "w2_rsu_income", "w2_federal_tax", "w2_state_tax",
    "w2_social_security", "w2_medicare", "w2_pretax_401k", "w2_roth_401k",
    "w2_employer_health", "w2_transit", "w2_cafeteria_125",
)
MORTGAGE_DB_FIELDS = (
    "mortgage_balance", "mortgage_rate", "mortgage_monthly_payment", "mortgage_original_amount",
    "mortgage_escrow_balance", "mortgage_principal_payment", "mortgage_interest_payment",
    "mortgage_escrow_payment", "mortgage_property_address",
)


class Finding(BaseModel):
    """One value read from a document."""

    field: str = Field(description="Label as printed on the document, e.g. 'Box 1 Wages'")
    value: str = Field(description="The value as displayed, e.g. '$197,700.00' or an address")
    value_numeric: float | None = Field(description="Numeric value in dollars or percent, null for text")
    category: str = Field(description="income | mortgage | retirement | account_balance | other")
    confidence: Confidence
    db_field: str | None = Field(description="The Tallied field this maps to, or null when none applies")


class IncomeExtraction(BaseModel):
    findings: list[Finding]


class MortgageExtraction(BaseModel):
    findings: list[Finding]


class GeneralExtraction(BaseModel):
    document_type: str = Field(description="W2 | pay stub | mortgage statement | 401(k) statement | bank statement | other")
    findings: list[Finding]


class RetirementHoldingExtraction(BaseModel):
    fund_name: str
    ticker: str | None
    balance: float | None
    allocation_pct: float | None
    gain_loss: float | None


class RetirementExtraction(BaseModel):
    plan_name: str | None
    provider: str | None
    statement_start: str | None = Field(description="YYYY-MM-DD")
    statement_end: str | None = Field(description="YYYY-MM-DD")
    total_balance: float | None
    vested_balance: float | None
    roth_balance: float | None
    pretax_balance: float | None
    employer_match_balance: float | None
    other_balance: float | None
    pretax_deferral_rate_pct: float | None = Field(description="Whole percent, 8 not 0.08")
    roth_deferral_rate_pct: float | None = Field(description="Whole percent")
    total_employee_contributions_lifetime: float | None
    total_employer_contributions_lifetime: float | None
    roth_basis: float | None
    account_return_pct: float | None = Field(description="Whole percent")
    return_period_start: str | None = Field(description="YYYY-MM-DD")
    estimated_monthly_income: float | None
    holdings: list[RetirementHoldingExtraction]


class VestEventExtraction(BaseModel):
    vest_period: int
    vest_date: str = Field(description="YYYY-MM-DD")
    shares: int
    fmv_at_vest: float | None = Field(description="Taxable gain / vested quantity for the period")
    shares_withheld: int | None
    shares_released: int | None
    total_taxes_paid: float | None
    is_actual: bool = Field(description="True when the period has vested (vested quantity > 0)")


class RSUGrantExtraction(BaseModel):
    grant_number: str
    symbol: str
    grant_date: str | None = Field(description="YYYY-MM-DD")
    total_shares: int | None
    vested_shares: int | None
    unvested_shares: int | None
    sellable_shares: int | None
    share_price: float | None = Field(description="Estimated market value / granted quantity")
    vest_events: list[VestEventExtraction]


class RSUExtraction(BaseModel):
    grants: list[RSUGrantExtraction]


ReceiptCategory = Literal[
    "Shopping", "Restaurants & Bars", "Entertainment & Recreation", "Bills & Utilities",
    "Auto & Transport", "Travel", "Medical", "Personal", "Home Improvement", "Groceries",
    "Subscriptions", "Transfer", "Uncategorized",
]


class ReceiptItem(BaseModel):
    name: str
    qty: int | None
    price: float | None


class ReceiptExtraction(BaseModel):
    parse_error: str | None = Field(description="Why this email is not a receipt, else null")
    merchant: str | None
    amount: float | None = Field(description="Order subtotal before tax and shipping, positive")
    date: str | None = Field(description="YYYY-MM-DD")
    category: ReceiptCategory | None
    items: list[ReceiptItem]
    tax: float | None
    shipping: float | None
    order_id: str | None
    is_refund: bool


class VehicleValuation(BaseModel):
    current_value: int = Field(description="Private-party fair market value today, whole dollars")
    confidence: Confidence
    annual_depreciation_pct: float = Field(description="Expected yearly value loss over the next five years, as a percent between 0 and 60")
    reasoning: str = Field(description="Two or three sentences on the main factors")


class PropertyOutlook(BaseModel):
    annual_appreciation_pct: float = Field(description="Expected yearly appreciation over the next eight years, percent, typically -5 to 10")
    confidence: Confidence
    commentary: str = Field(description="Two or three sentences on the location, recent trend and outlook")
