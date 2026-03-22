"""
MCP server that wraps the Personal Finance FastAPI backend.
Allows Claude to query and test all API endpoints directly.

Usage: python mcp_server.py
Expects FastAPI backend running at http://localhost:8000
"""

import json
import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = "http://localhost:8000"

mcp = FastMCP("personal-finance-api")


def _get(path: str, params: dict | None = None) -> Any:
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        r = client.get(path, params={k: v for k, v in (params or {}).items() if v is not None})
        r.raise_for_status()
        return r.json()


def _post(path: str, body: dict) -> Any:
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        r = client.post(path, json=body)
        r.raise_for_status()
        return r.json()


def _put(path: str, body: dict) -> Any:
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        r = client.put(path, json=body)
        r.raise_for_status()
        return r.json()


def _delete(path: str) -> Any:
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        r = client.delete(path)
        r.raise_for_status()
        return r.json()


# ─── Health ────────────────────────────────────────────────────────────────

@mcp.tool()
def health_check() -> str:
    """Check if the backend API is running."""
    try:
        result = _get("/api/health")
        return json.dumps(result)
    except Exception as e:
        return f"Backend not reachable: {e}"


# ─── Snapshot ──────────────────────────────────────────────────────────────

@mcp.tool()
def get_snapshot() -> str:
    """Get the current financial snapshot — liquidity layers, net worth, liquid net worth, 12-month change."""
    return json.dumps(_get("/api/snapshot"), indent=2)


# ─── Accounts ─────────────────────────────────────────────────────────────

@mcp.tool()
def list_accounts(account_type: str | None = None, display_group: str | None = None) -> str:
    """List all financial accounts with their current balances. Optionally filter by account_type or display_group."""
    return json.dumps(_get("/api/accounts/", {"account_type": account_type, "display_group": display_group}), indent=2)


@mcp.tool()
def get_account(account_id: str) -> str:
    """Get a single account by ID with its current balance."""
    return json.dumps(_get(f"/api/accounts/{account_id}"), indent=2)


@mcp.tool()
def get_balance_history(account_id: str, from_date: str | None = None, to_date: str | None = None) -> str:
    """Get balance history for a specific account. Dates in YYYY-MM-DD format."""
    return json.dumps(_get(f"/api/accounts/{account_id}/balances", {"from_date": from_date, "to_date": to_date}))


# ─── Transactions ─────────────────────────────────────────────────────────

@mcp.tool()
def list_transactions(
    from_date: str | None = None,
    to_date: str | None = None,
    category: str | None = None,
    merchant: str | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> str:
    """List transactions with filters. Dates in YYYY-MM-DD format."""
    return json.dumps(_get("/api/transactions/", {
        "from_date": from_date, "to_date": to_date,
        "category": category, "merchant": merchant,
        "search": search, "limit": limit, "offset": offset,
    }), indent=2)


# ─── Spending ─────────────────────────────────────────────────────────────

@mcp.tool()
def spending_by_category(from_date: str | None = None, to_date: str | None = None) -> str:
    """Get spending totals grouped by category for a date range."""
    return json.dumps(_get("/api/spending/by-category", {"from_date": from_date, "to_date": to_date}), indent=2)


@mcp.tool()
def spending_recurring() -> str:
    """Get detected recurring expenses."""
    return json.dumps(_get("/api/spending/recurring"), indent=2)


@mcp.tool()
def spending_monthly_trend() -> str:
    """Get monthly spending totals over time."""
    return json.dumps(_get("/api/spending/monthly-trend"), indent=2)


# ─── Trends ───────────────────────────────────────────────────────────────

@mcp.tool()
def net_worth_trend(from_date: str | None = None, to_date: str | None = None) -> str:
    """Get net worth by group over time. Returns time series data."""
    return json.dumps(_get("/api/trends/net-worth", {"from_date": from_date, "to_date": to_date}), indent=2)


@mcp.tool()
def cash_flow_trend() -> str:
    """Get monthly cash flow (balance changes by account type)."""
    return json.dumps(_get("/api/trends/cash-flow"), indent=2)


# ─── Income ───────────────────────────────────────────────────────────────

@mcp.tool()
def income_history() -> str:
    """Get W2 records across years and RSU grant summary."""
    return json.dumps(_get("/api/income/history"), indent=2)


@mcp.tool()
def income_current() -> str:
    """Get current year income breakdown."""
    return json.dumps(_get("/api/income/current"), indent=2)


@mcp.tool()
def create_w2(
    tax_year: int,
    gross_pay: float,
    base_salary: float | None = None,
    rsu_income: float | None = None,
) -> str:
    """Create or update a W2 record for a given tax year."""
    body: dict = {"tax_year": tax_year, "gross_pay": gross_pay}
    if base_salary is not None:
        body["base_salary"] = base_salary
    if rsu_income is not None:
        body["rsu_income"] = rsu_income
    return json.dumps(_post("/api/income/w2", body), indent=2)


# ─── Planning ─────────────────────────────────────────────────────────────

@mcp.tool()
def list_plans() -> str:
    """List all saved financial plans."""
    return json.dumps(_get("/api/plans/"), indent=2)


@mcp.tool()
def get_plan(plan_id: int) -> str:
    """Get a plan with its assumptions and year-by-year projections."""
    return json.dumps(_get(f"/api/plans/{plan_id}"), indent=2)


@mcp.tool()
def create_plan(name: str, scenario_type: str = "base") -> str:
    """Create a new financial plan with default assumptions. scenario_type: base|optimistic|pessimistic|custom."""
    return json.dumps(_post("/api/plans/", {"name": name, "scenario_type": scenario_type, "assumptions": []}), indent=2)


@mcp.tool()
def update_plan_assumptions(plan_id: int, assumptions_json: str) -> str:
    """Update a plan's assumptions and recompute projections. assumptions_json is a JSON array of {key, value} objects."""
    assumptions = json.loads(assumptions_json)
    return json.dumps(_put(f"/api/plans/{plan_id}", {"assumptions": assumptions}), indent=2)


@mcp.tool()
def plan_sensitivity(plan_id: int) -> str:
    """Run sensitivity analysis on a plan — shows which assumptions have the biggest impact on outcomes."""
    return json.dumps(_get(f"/api/plans/{plan_id}/sensitivity"), indent=2)


@mcp.tool()
def plan_variance(plan_id: int) -> str:
    """Get plan vs actuals variance report."""
    return json.dumps(_get(f"/api/plans/{plan_id}/variance"), indent=2)


# ─── Import ───────────────────────────────────────────────────────────────

@mcp.tool()
def import_log() -> str:
    """Get the import audit trail — shows all data imports and their status."""
    return json.dumps(_get("/api/import/log"), indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
