"""Pydantic schemas for everything Claude is asked to produce (structured outputs)."""
from __future__ import annotations

from typing import Literal, Optional

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
    value_numeric: Optional[float] = Field(description="Numeric value in dollars or percent, null for text")
    category: str = Field(description="income | mortgage | retirement | account_balance | other")
    confidence: Confidence
    db_field: Optional[str] = Field(description="The Tallied field this maps to, or null when none applies")


class IncomeExtraction(BaseModel):
    findings: list[Finding]


class MortgageExtraction(BaseModel):
    findings: list[Finding]


class GeneralExtraction(BaseModel):
    document_type: str = Field(description="W2 | pay stub | mortgage statement | 401(k) statement | bank statement | other")
    findings: list[Finding]


class RetirementHoldingExtraction(BaseModel):
    fund_name: str
    ticker: Optional[str]
    balance: Optional[float]
    allocation_pct: Optional[float]
    gain_loss: Optional[float]


class RetirementExtraction(BaseModel):
    plan_name: Optional[str]
    provider: Optional[str]
    statement_start: Optional[str] = Field(description="YYYY-MM-DD")
    statement_end: Optional[str] = Field(description="YYYY-MM-DD")
    total_balance: Optional[float]
    vested_balance: Optional[float]
    roth_balance: Optional[float]
    pretax_balance: Optional[float]
    employer_match_balance: Optional[float]
    other_balance: Optional[float]
    pretax_deferral_rate_pct: Optional[float] = Field(description="Whole percent, 8 not 0.08")
    roth_deferral_rate_pct: Optional[float] = Field(description="Whole percent")
    total_employee_contributions_lifetime: Optional[float]
    total_employer_contributions_lifetime: Optional[float]
    roth_basis: Optional[float]
    account_return_pct: Optional[float] = Field(description="Whole percent")
    return_period_start: Optional[str] = Field(description="YYYY-MM-DD")
    estimated_monthly_income: Optional[float]
    holdings: list[RetirementHoldingExtraction]


class VestEventExtraction(BaseModel):
    vest_period: int
    vest_date: str = Field(description="YYYY-MM-DD")
    shares: int
    fmv_at_vest: Optional[float] = Field(description="Taxable gain / vested quantity for the period")
    shares_withheld: Optional[int]
    shares_released: Optional[int]
    total_taxes_paid: Optional[float]
    is_actual: bool = Field(description="True when the period has vested (vested quantity > 0)")


class RSUGrantExtraction(BaseModel):
    grant_number: str
    symbol: str
    grant_date: Optional[str] = Field(description="YYYY-MM-DD")
    total_shares: Optional[int]
    vested_shares: Optional[int]
    unvested_shares: Optional[int]
    sellable_shares: Optional[int]
    share_price: Optional[float] = Field(description="Estimated market value / granted quantity")
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
    qty: Optional[int]
    price: Optional[float]


class ReceiptExtraction(BaseModel):
    parse_error: Optional[str] = Field(description="Why this email is not a receipt, else null")
    merchant: Optional[str]
    amount: Optional[float] = Field(description="Order subtotal before tax and shipping, positive")
    date: Optional[str] = Field(description="YYYY-MM-DD")
    category: Optional[ReceiptCategory]
    items: list[ReceiptItem]
    tax: Optional[float]
    shipping: Optional[float]
    order_id: Optional[str]
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
