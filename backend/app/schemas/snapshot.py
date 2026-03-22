from datetime import date

from pydantic import BaseModel


class LayerAccount(BaseModel):
    id: str
    name: str
    balance: float


class LiquidityLayer(BaseModel):
    name: str  # e.g. "Cash"
    total: float
    accounts: list[LayerAccount]


class SnapshotResponse(BaseModel):
    layers: list[LiquidityLayer]
    net_worth: float
    liquid_net_worth: float
    total_comp_annual: float | None = None
    net_worth_12mo_change: float | None = None


class IncomeBreakdown(BaseModel):
    salary: float
    rsu_income: float
    total_comp: float
    rsu_pct: float


class BalanceHistory(BaseModel):
    dates: list[date]
    balances: list[float]


class NetWorthSeries(BaseModel):
    dates: list[str]
    groups: dict[str, list[float]]  # keyed by display_group
    totals: list[float]
