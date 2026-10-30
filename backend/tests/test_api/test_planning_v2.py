"""Planning v2 routes: household, outlook, what-if, life events, sprint (docs/requirements/planning-v2.md)."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.income import W2Record
from app.models.investment import RSUGrant, StockPrice, VestEvent
from app.models.planning import PlanAssumption
from app.models.property import Mortgage
from app.models.retirement import RetirementAccount
from app.models.transaction import Transaction
from tests.conftest import set_household_age


def _plan(client, **assumptions):
    res = client.post("/api/v1/plans/", json={"name": "Test", "assumptions": [
        {"key": k, "value": v} for k, v in assumptions.items()
    ]})
    assert res.status_code == 201, res.text
    return res.json()


def _household(db, with_spending: bool = False):
    today = date.today()
    for aid, group, atype, bal in [
        ("chk", "Cash", "cash", 40_000), ("brk", "Investments", "investment_stock", 45_000),
        ("k401", "Retirement", "investment_401k", 185_000),
    ]:
        db.add(Account(id=aid, name=aid, account_type=atype, display_group=group, include_in_nw=True))
        db.add(BalanceSnapshot(account_id=aid, snapshot_date=today, balance=Decimal(bal), source="test"))
    # A gross-only W-2 (the production shape): salary must come from gross minus that year's vests.
    db.add(W2Record(tax_year=today.year - 1, gross_pay=Decimal("210000")))
    db.add(RSUGrant(id="G1", company="Microsoft", symbol="MSFT", grant_date=date(today.year - 2, 5, 15),
                    total_shares=900, vested_shares=300, unvested_shares=600, sellable_shares=200,
                    share_price=Decimal("100")))
    db.add(VestEvent(grant_id="G1", vest_date=date(today.year - 1, 5, 15), vest_period=1, shares=300,
                     fmv_at_vest=Decimal("216.66"), is_actual=True))
    for k in (1, 2):
        db.add(VestEvent(grant_id="G1", vest_date=today + timedelta(days=200 + 365 * (k - 1)), vest_period=k + 1,
                         shares=300, is_actual=False))
    db.add(StockPrice(symbol="MSFT", price_date=today, close_price=Decimal("100"), source="seed"))
    db.add(RetirementAccount(plan_name="Test 401(k)", provider="Test", total_balance=Decimal("185000"),
                             roth_basis=Decimal("30000"), statement_end=today))
    if with_spending:
        db.add(Account(id="card", name="card", account_type="credit_card", display_group="Credit Cards", include_in_nw=False))
        for m in range(12):
            d = today - timedelta(days=15 + 30 * m)
            db.add(Transaction(id=f"g{m}", account_id="card", date=d, amount=Decimal("-3000"), category="Groceries"))
            db.add(Transaction(id=f"f{m}", account_id="card", date=d, amount=Decimal("-200"), category="Gas"))
            db.add(Transaction(id=f"u{m}", account_id="card", date=d, amount=Decimal("-100"), category=None))
        db.add(Transaction(id="spike", account_id="card", date=today - timedelta(days=40), amount=Decimal("-9000"),
                           category="Travel", merchant="Big trip"))
        db.add(Transaction(id="xfer", account_id="card", date=today - timedelta(days=20), amount=Decimal("-5000"),
                           category="Transfer"))
    db.commit()


def test_no_age_is_assumed_until_the_birth_date_is_set(client, db_session):
    assert client.get("/api/v1/plans/household").json() == {"birth_date": None, "age": None}
    plan = _plan(client)
    res = client.get(f"/api/v1/plans/{plan['id']}/outlook", params={"analysis": "false"})
    assert res.status_code == 422 and "birth date" in res.text
    assert client.post(f"/api/v1/plans/{plan['id']}/what-if", json={}).status_code == 422
    assert client.put("/api/v1/plans/household", json={"birth_date": "2999-01-01"}).status_code == 422

    set_household_age(client, 41)
    assert client.get("/api/v1/plans/household").json()["age"] == 41
    out = client.get(f"/api/v1/plans/{plan['id']}/outlook", params={"analysis": "false"}).json()
    assert out["current_age"] == 41 and out["birth_date"] == f"{date.today().year - 41}-01-01"
    assert "social_security" in {w["key"] for w in out["warnings"]}
    assert {m["label"] for m in out["milestones"]} >= {"55", "59½", "62", "65", "67", "70"}
    # Setting the birth date stores the plan line for plans created before it.
    assert client.get(f"/api/v1/plans/{plan['id']}").json()["projections"][0]["age"] == 41


def test_outlook_starts_from_the_household_and_income_does_not_stop_after_the_last_vest(client, db_session, born_30):
    _household(db_session)
    plan = _plan(client, retirement_age=50)
    out = client.get(f"/api/v1/plans/{plan['id']}/outlook", params={"analysis": "false"}).json()

    sp = out["starting_point"]
    assert out["current_age"] == 30
    assert sp["comp_source"] == "vests"
    assert sp["rsu_income"] == 64_998.0 and sp["salary"] == 145_002.0   # 210k gross - 300 x 216.66
    assert sp["company_stock"] == 20_000.0                              # 200 sellable x $100
    assert sp["scheduled_vest_value"] == 60_000.0 and sp["scheduled_vest_count"] == 2
    assert sp["investable"] == 40_000 + 45_000 + 20_000 + 185_000
    assert sp["roth_basis"] == 30_000 and sp["full_retirement_age"] == 67

    rows = out["rows"]
    working = [r for r in rows if r["phase"] == "working"]
    assert len(working) == 20 and rows[20]["age"] == 50
    assert all(r["salary"] > 0 and r["rsu_income"] > 0 for r in working)   # the October $0 defect
    assert 0 <= out["summary"]["success_rate"] <= 1
    assert len(out["fan"]["liquid"]["p50"]) == len(rows) == 95 - 30 + 1
    assert out["fan"]["liquid"]["p10"][25] <= out["fan"]["liquid"]["p50"][25] <= out["fan"]["liquid"]["p90"][25]
    # Retired at 50 with a 30k Roth basis: the bridge draws taxable first, then the Roth basis, before 59½.
    retired = [r for r in rows if r["phase"] == "retired" and r["age"] < 60]
    assert retired and retired[0]["healthcare"] > 0        # marketplace cover before Medicare
    assert any(r["src_roth_basis"] > 0 for r in retired) or all(r["src_401k_penalty"] == 0 for r in retired)

    stored = client.get(f"/api/v1/plans/{plan['id']}").json()["projections"]
    assert stored[5]["salary"] == rows[5]["salary"]


def test_what_will_retirement_cost_is_built_from_actual_spending(client, db_session, born_30):
    _household(db_session, with_spending=True)
    plan = _plan(client)
    b = client.get(f"/api/v1/plans/{plan['id']}/outlook", params={"analysis": "false"}).json()["spending_builder"]
    # 12 x (3000 + 200 + 100) + 9000 spike; the transfer is not spending (D1).
    assert b["trailing_total"] == 12 * 3300 + 9000
    assert b["spike_total"] == 9000 and b["spikes"][0]["merchant"] == "Big trip"
    assert b["uncategorised"] == 1200 and b["work_costs"] == 2400
    assert b["suggested"] == round(12 * 3300 - 2400 * 0.5, -2)           # spikes out, half the commute stops
    assert b["range"]["high"] == round(12 * 3300 + 9000, -2)
    assert b["references"]["bls"]["age_65_plus"] == 61_432
    assert b["health"]["post65"] == 8_500


def test_what_if_changes_the_answer_and_writes_nothing(client, db_session, born_30):
    _household(db_session)
    plan = _plan(client, retirement_age=55)
    url = f"/api/v1/plans/{plan['id']}/what-if"
    base = client.post(url, json={"analysis": False}).json()["summary"]["success_rate"]
    cheaper = client.post(url, json={"overrides": {"retirement_spending": 50_000}, "analysis": False}).json()
    assert cheaper["summary"]["success_rate"] >= base
    assert cheaper["values"]["retirement_spending"] == 50_000
    smile = client.post(url, json={"spending_profile": "smile", "analysis": False}).json()
    assert smile["plan"]["spending_profile"] == "smile"
    stored = db_session.query(PlanAssumption).filter_by(plan_id=plan["id"], key="retirement_spending").one()
    assert float(stored.value) == 100_000

    assert client.post(url, json={"overrides": {"nonsense": 1}}).status_code == 422
    assert client.post(url, json={"overrides": {"current_age": 30}}).status_code == 422   # gone from the vocabulary
    assert client.post(url, json={"spending_rule": "yolo"}).status_code == 422
    assert client.post(url, json={"spending_profile": "frown"}).status_code == 422
    assert client.post(url, json={"regime": "martian"}).status_code == 422
    clamped = client.post(url, json={"overrides": {"retirement_age": 500}, "analysis": False}).json()
    assert clamped["retirement_age"] == 80


def test_analysis_has_scenarios_goal_seek_sensitivity_and_nest_egg(client, db_session, born_30):
    _household(db_session)
    plan = _plan(client, retirement_age=55)
    out = client.get(f"/api/v1/plans/{plan['id']}/outlook", params={"regime": "stagflation"}).json()
    keys = [s["key"] for s in out["scenarios"]]
    assert keys[0] == "base" and {"stagflation", "lost_decade", "high_inflation", "strong_start"} <= set(keys)
    g = out["goal_seek"]
    assert g["target"] == 0.85 and g["by_age"] and g["by_spending"]
    assert {"median_at_retirement", "median_at_end"} <= set(g["by_age"][0])
    # Goal-seek follows the selected scenario: under stagflation the base chance matches that scenario's.
    stag = next(s for s in out["scenarios"] if s["key"] == "stagflation")
    assert abs(g["base_success"] - stag["success_rate"]) < 0.08
    assert out["sensitivity"] and all("success_low" in s for s in out["sensitivity"])
    assert out["summary"]["historical_cohorts"] == len(out["cohorts"]) > 0
    egg = out["nest_egg"]
    assert egg["need_first_year"] > 0 and [r["horizon"] for r in egg["rows"]][:4] == [30, 40, 41, 50] or egg["rows"]
    thirty = next(r for r in egg["rows"] if r["horizon"] == 30)
    assert 0.03 < thirty["fixed_worst"] < 0.045 and thirty["nest_egg_fixed_worst"] > thirty["nest_egg_fixed_p10"]


def test_life_events_crud_impact_and_layoff_outcome(client, db_session, born_30):
    _household(db_session)
    plan = _plan(client, retirement_age=55)
    res = client.post(f"/api/v1/plans/{plan['id']}/events", json={
        "kind": "one_off_expense", "label": "Big purchase", "start_age": 33, "amount": 200_000})
    assert res.status_code == 201, res.text
    ev = res.json()
    lay = client.post(f"/api/v1/plans/{plan['id']}/events", json={
        "kind": "layoff", "label": "Layoff, never re-employed", "start_age": 40,
        "params": {"never_reemployed": 1, "severance_weeks": 12}}).json()
    assert lay["params"] == {"never_reemployed": 1.0, "severance_weeks": 12.0}
    out = client.get(f"/api/v1/plans/{plan['id']}/outlook").json()
    assert [e["label"] for e in out["events"]] == ["Big purchase", "Layoff, never re-employed"]
    impact = next(i for i in out["event_impacts"] if i["id"] == ev["id"])
    assert impact["success_without"] >= impact["success_with"]
    outcome = next(o for o in out["event_outcomes"] if o["id"] == lay["id"])
    assert outcome["income_window"] == [40, 54]
    assert out["retirement_age"] == 40 and out["planned_retirement_age"] == 55   # no next job: retired at 40
    assert outcome["income_for_plan_line"] is None or outcome["income_for_plan_line"] >= 0
    if outcome["plan_line_runs_out_at"] is not None:
        assert outcome["income_for_plan_line"] is None or outcome["income_for_plan_line"] > 0

    # Toggling in a what-if does not touch the saved event.
    off = client.post(f"/api/v1/plans/{plan['id']}/what-if", json={"event_enabled": {str(ev["id"]): False}, "analysis": False}).json()
    assert off["events"][0]["enabled"] is False
    assert client.get(f"/api/v1/plans/{plan['id']}").json()["events"][0]["enabled"] is True

    assert client.put(f"/api/v1/plans/events/{ev['id']}", json={"enabled": False}).json()["enabled"] is False
    assert client.put(f"/api/v1/plans/events/{lay['id']}", json={"params": {"gap_months": 9}}).json()["params"]["gap_months"] == 9
    bad = [
        {"kind": "teleport", "label": "x", "start_age": 40},
        {"kind": "part_time", "label": "x", "start_age": 60, "end_age": 50},
        {"kind": "layoff", "label": "x", "start_age": 40, "params": {"bonus": 1}},
        {"kind": "layoff", "label": "x", "start_age": 40, "params": {"gap_months": 999}},
        {"kind": "windfall", "label": "x", "start_age": 40, "params": {"gap_months": 1}},
    ]
    for body in bad:
        assert client.post(f"/api/v1/plans/{plan['id']}/events", json=body).status_code == 422, body
    assert client.delete(f"/api/v1/plans/events/{ev['id']}").status_code == 204
    assert client.delete(f"/api/v1/plans/events/{ev['id']}").status_code == 404


def test_sprint_to_retirement_grid_and_levers(client, db_session, born_30):
    _household(db_session)
    plan = _plan(client, retirement_age=55, retirement_spending=60_000)
    s = client.post(f"/api/v1/plans/{plan['id']}/sprint", json={}).json()
    assert s["shifts"] == [-0.02, -0.01, 0.0, 0.01]
    grid = s["grid"]
    assert grid[0]["age"] >= 31 and len(grid[0]["max_spending"]) == 4
    # More years of work and better returns can only allow more spending.
    col = [r["max_spending"][2] or 0 for r in grid]
    assert col == sorted(col)
    assert all((r["max_spending"][0] or 0) <= (r["max_spending"][3] or 0) for r in grid)
    labels = {lv["label"] for lv in s["levers"]}
    assert labels == {"Living spending", "Returns", "Pay after a job change", "New equity grants", "Gap between jobs"}
    assert s["job_change"]["synthetic"] is True
    assert s["by_spending"] and "earliest_age" in s["by_spending"][0]


def test_save_spending_rule_profile_and_copy_a_plan(client, db_session, born_30):
    _household(db_session)
    plan = _plan(client)
    client.post(f"/api/v1/plans/{plan['id']}/events", json={"kind": "part_time", "label": "Consulting", "start_age": 60,
                                                            "end_age": 63, "amount": 30_000})
    res = client.put(f"/api/v1/plans/{plan['id']}", json={"spending_rule": "guardrails", "spending_profile": "smile",
                                                           "assumptions": [{"key": "retirement_age", "value": 52}]})
    assert res.status_code == 200, res.text
    saved = res.json()
    assert saved["spending_rule"] == "guardrails" and saved["spending_profile"] == "smile"
    values = {a["key"]: a["value"] for a in saved["assumptions"]}
    assert values["retirement_age"] == 52 and values["retirement_spending"] == 100_000  # others kept
    assert "current_age" not in values
    assert client.put(f"/api/v1/plans/{plan['id']}", json={"spending_rule": "nope"}).status_code == 422

    copy = client.post("/api/v1/plans/", json={"name": "Copy", "copy_from": plan["id"]}).json()
    assert copy["spending_rule"] == "guardrails" and copy["spending_profile"] == "smile"
    assert {a["key"]: a["value"] for a in copy["assumptions"]}["retirement_age"] == 52
    assert [e["label"] for e in copy["events"]] == ["Consulting"]


def test_escrow_continues_after_the_mortgage_is_paid_off(client, db_session, born_30):
    _household(db_session)
    db_session.add(Account(id="house", name="house", account_type="real_estate", display_group="Home Equity", include_in_nw=True))
    db_session.add(BalanceSnapshot(account_id="house", snapshot_date=date.today(), balance=Decimal("200000"), source="t"))
    db_session.add(Mortgage(account_id="house", original_amount=Decimal("300000"), current_balance=Decimal("50000"),
                            rate=Decimal("0.04"), monthly_payment=Decimal("2000"), escrow=Decimal("500")))
    db_session.commit()
    plan = _plan(client, retirement_age=32)
    out = client.get(f"/api/v1/plans/{plan['id']}/outlook", params={"analysis": "false"}).json()
    assert out["starting_point"]["escrow_monthly"] == 500
    late = next(r for r in out["rows"] if r["age"] == 70)
    assert late["housing"] > 0 and abs(late["housing"] / (late["deflator"] / 1.03) - 6000) < 600   # escrow only, ~$6,000 today
    payoff = client.post(f"/api/v1/plans/{plan['id']}/what-if", json={"overrides": {"payoff_mortgage": 1}, "analysis": False}).json()
    first = next(r for r in payoff["rows"] if r["age"] == 32)
    assert first["mortgage_payoff"] > 0


def test_catalogue_lists_rules_profiles_scenarios_and_templates(client):
    cat = client.get("/api/v1/plans/catalogue").json()
    assert [r["key"] for r in cat["spending_rules"]] == ["fixed", "guardrails", "vpw"]
    assert [r["key"] for r in cat["spending_profiles"]] == ["flat", "smile"]
    kinds = {t["kind"] for t in cat["event_templates"]}
    assert {"part_time", "layoff", "acquisition", "downsize", "recurring_expense"} <= kinds
    assert cat["layoff_defaults"]["ui_weekly"] == 1105
    keys = {a["key"] for a in cat["assumptions"]}
    assert "ss_claim_age" in keys and "current_age" not in keys and "birth_year" not in keys


def test_migration_backfills_the_same_keys_the_vocabulary_adds():
    import importlib.util
    from pathlib import Path

    from app.services.plan_assumptions import BY_KEY, REMOVED_KEYS, V2_KEYS

    path = Path(__file__).parents[2] / "alembic" / "versions" / "0005planv2_plan_events_spending_rule.py"
    spec = importlib.util.spec_from_file_location("m0005", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    frozen = {k: v for k, _, _, v, _, _ in mod.NEW_ASSUMPTIONS}
    assert set(frozen) == set(V2_KEYS)
    assert all(frozen[k] == BY_KEY[k]["value"] for k in V2_KEYS)
    assert list(REMOVED_KEYS) == mod.REMOVED_KEYS and not set(REMOVED_KEYS) & set(BY_KEY)
