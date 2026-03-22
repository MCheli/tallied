from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


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
    assumptions: list[AssumptionInput]


class PlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    assumptions: list[AssumptionInput] | None = None


class AssumptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    display_name: str
    category: str
    value: float
    description: str
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
    assumptions: list[AssumptionResponse]
    projections: list[ProjectionRow]
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
