from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class AssumptionInput(BaseModel):
    key: str
    value: float
    display_name: str | None = None
    description: str | None = None
    category: str | None = None
    sensitivity: str | None = None


class PlanCreate(BaseModel):
    name: str
    description: str | None = None
    scenario_type: str = "base"
    spending_rule: str = "fixed"
    spending_profile: str = "flat"
    assumptions: list[AssumptionInput] = []
    copy_from: int | None = None  # start from another plan's assumptions, rule and events


class PlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    spending_rule: str | None = None
    spending_profile: str | None = None
    assumptions: list[AssumptionInput] | None = None


class HouseholdResponse(BaseModel):
    birth_date: date | None = None
    age: int | None = None


class HouseholdUpdate(BaseModel):
    birth_date: date


class PlanEventInput(BaseModel):
    kind: str
    label: str = Field(min_length=1, max_length=120)
    start_age: int = Field(ge=0, le=120)
    end_age: int | None = Field(default=None, ge=0, le=120)
    amount: float = 0
    pct: float = Field(default=0, ge=-1, le=10)
    enabled: bool = True
    params: dict[str, float] | None = None


class PlanEventUpdate(BaseModel):
    kind: str | None = None
    label: str | None = Field(default=None, min_length=1, max_length=120)
    start_age: int | None = Field(default=None, ge=0, le=120)
    end_age: int | None = Field(default=None, ge=0, le=120)
    amount: float | None = None
    pct: float | None = Field(default=None, ge=-1, le=10)
    enabled: bool | None = None
    params: dict[str, float] | None = None


class PlanEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    kind: str
    label: str
    start_age: int
    end_age: int | None = None
    amount: float
    pct: float
    enabled: bool
    params: dict[str, float] | None = None


class WhatIfRequest(BaseModel):
    """Levers to try without saving: assumption overrides, spending rule, scenario, events on/off."""
    overrides: dict[str, float] = {}
    spending_rule: str | None = None
    spending_profile: str | None = None
    regime: str = "base"
    event_enabled: dict[int, bool] = {}
    analysis: bool = True


class AssumptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    display_name: str
    category: str
    value: float
    description: str | None = None
    sensitivity: str


class ProjectionRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    age: int
    phase: str
    salary: float
    rsu_income: float
    total_comp: float
    cash: float
    investments: float
    company_stock: float
    home_equity: float
    retirement_bal: float
    net_worth: float
    withdrawal: float


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    scenario_type: str
    is_active: bool
    spending_rule: str = "fixed"
    spending_profile: str = "flat"
    assumptions: list[AssumptionResponse]
    projections: list[ProjectionRow]
    events: list[PlanEventResponse] = []
    created_at: datetime
    updated_at: datetime


class PlanListItem(BaseModel):
    id: int
    name: str
    scenario_type: str
    is_active: bool
    created_at: datetime


class VarianceMetric(BaseModel):
    plan: float
    forecast: float | None = None
    actual: float
    plan_var_pct: float
    forecast_var_pct: float | None = None


class VarianceResponse(BaseModel):
    year: int
    metrics: dict[str, VarianceMetric]


class SensitivityItem(BaseModel):
    key: str
    display_name: str
    base_value: float
    impact_low: float
    impact_high: float


class SensitivityResponse(BaseModel):
    items: list[SensitivityItem]
    target_metric: str
    target_year: int


class PlanCompareResponse(BaseModel):
    plans: list[PlanResponse]


class ActualSnapshotCreate(BaseModel):
    snapshot_date: date
    cash: float
    investments: float
    company_stock: float
    home_equity: float
    retirement_bal: float
    net_worth: float
    salary_ytd: float | None = None
    rsu_income_ytd: float | None = None
    total_comp_ytd: float | None = None
    notes: str | None = None


class ActualSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    snapshot_date: date
    cash: float
    investments: float
    company_stock: float
    home_equity: float
    retirement_bal: float
    net_worth: float
    salary_ytd: float | None = None
    rsu_income_ytd: float | None = None
    total_comp_ytd: float | None = None
    notes: str | None = None
    created_at: datetime
