"""Categorization by merchant rules; the owner's choices are never overwritten (SPEND-CAT-001)."""
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.models.category_rule import CategoryRule
from app.models.transaction import Transaction
from app.services.categorize import apply_rules


def _setup(db):
    db.add_all([
        Account(id="card", name="Card", account_type="credit_card", display_group="Credit Cards", include_in_nw=True, is_active=True),
        Account(id="chk", name="Checking", account_type="cash", display_group="Cash", include_in_nw=True, is_active=True),
        Account(id="loan", name="Mortgage", account_type="loan_mortgage", display_group="Home Equity", include_in_nw=True, is_active=True),
    ])
    db.flush()
    rows = [
        ("t1", "card", -12.50, "Dunkin'"), ("t2", "card", -45.00, "Shell Oil 1234"), ("t3", "card", 900.00, "Payment"),
        ("t4", "loan", 3074.70, "Payment"), ("t5", "chk", 4000.00, "Inc Payroll"), ("t6", "card", -80.00, "Mystery Shop"),
        ("t7", "card", -30.00, "Shell"),
    ]
    db.add_all([Transaction(id=i, account_id=a, date=date(2026, 10, 1), amount=Decimal(str(v)), merchant=m, source="test") for i, a, v, m in rows])
    db.add_all([
        CategoryRule(pattern="dunkin", match="contains", category="Coffee Shops", category_group="Food & Dining", source="research"),
        CategoryRule(pattern="shell", match="contains", category="Gas", category_group="Auto & Transport", source="research"),
        CategoryRule(pattern="shell oil", match="prefix", category="Heating Oil", category_group="Housing", source="research"),
        CategoryRule(pattern="payment", match="exact", account_type="credit_card", direction="in",
                     category="Credit Card Payment", category_group="Transfers", source="research"),
        CategoryRule(pattern="payment", match="exact", account_type="loan_mortgage", direction="in",
                     category="Mortgage Payment", category_group="Transfers", source="research"),
        CategoryRule(pattern="inc payroll", match="exact", category="Paycheck", category_group="Income", source="research"),
    ])
    db.commit()


def test_rules_apply_by_specificity_account_type_and_direction(db_session):
    _setup(db_session)
    assert apply_rules(db_session) == 6
    got = {t.id: (t.category, t.category_source) for t in db_session.query(Transaction).all()}
    assert got["t1"] == ("Coffee Shops", "rule:research")
    assert got["t2"] == ("Heating Oil", "rule:research")     # prefix beats contains
    assert got["t7"] == ("Gas", "rule:research")
    assert got["t3"][0] == "Credit Card Payment"              # same text, different account type
    assert got["t4"][0] == "Mortgage Payment"
    assert got["t5"][0] == "Paycheck"
    assert got["t6"] == (None, None)                          # no rule: stays uncategorized, never guessed


def test_the_owners_category_survives_rules(client, db_session):
    _setup(db_session)
    apply_rules(db_session)
    db_session.commit()
    r = client.put("/api/v1/transactions/t1", json={"category": "Restaurants", "category_group": "Food & Dining"})
    assert r.status_code == 200 and r.json()["category_source"] == "manual"
    # A new rule for the same merchant re-derives rule-set rows but leaves the owner's choice alone.
    r = client.post("/api/v1/transactions/category-rules", json={
        "pattern": "Shell", "match": "exact", "category": "Fuel", "category_group": "Auto & Transport"})
    assert r.status_code == 201 and r.json()["recategorized"] == 1
    db_session.expire_all()
    assert db_session.get(Transaction, "t1").category == "Restaurants"
    assert (db_session.get(Transaction, "t7").category, db_session.get(Transaction, "t7").category_source) == ("Fuel", "rule:manual")
    cats = {c["category"] for c in client.get("/api/v1/transactions/categories").json()}
    assert {"Restaurants", "Fuel", "Paycheck"} <= cats


def test_email_categories_are_protected_and_bad_rules_rejected(client, db_session):
    _setup(db_session)
    t = db_session.get(Transaction, "t6")
    t.category, t.category_group, t.category_source = "Electronics", "Shopping", "email"
    db_session.commit()
    db_session.add(CategoryRule(pattern="mystery", match="contains", category="Shopping", category_group="Shopping", source="research"))
    db_session.commit()
    apply_rules(db_session, rederive=True)
    assert db_session.get(Transaction, "t6").category == "Electronics"
    r = client.post("/api/v1/transactions/category-rules", json={"pattern": "x", "match": "regex", "category": "A", "category_group": "B"})
    assert r.status_code == 422
