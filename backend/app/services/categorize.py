"""Transaction categorization by merchant rules (the sync provider sends no categories).

A rule matches on the merchant text (exact, prefix or contains, case-insensitive), optionally
only for one account type and one direction (money out or in). Rules are tried by priority,
then exact before prefix before contains, then longer patterns first.

A category the owner set by hand ("manual") or one confirmed from a receipt ("email") is
never overwritten. Rule-set categories can be re-derived when the rules change.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.category_rule import CategoryRule
from app.models.transaction import Transaction

logger = logging.getLogger("tallied.categorize")

PROTECTED_SOURCES = ("manual", "email")
_MATCH_ORDER = {"exact": 0, "prefix": 1, "contains": 2}


def _ordered(rules: Iterable[CategoryRule]) -> list[CategoryRule]:
    return sorted(rules, key=lambda r: (-(r.priority or 0), _MATCH_ORDER.get(r.match, 3), -len(r.pattern)))


def rule_matches(rule: CategoryRule, merchant: str | None, account_type: str | None, amount: float | None) -> bool:
    text = (merchant or "").strip().lower()
    pattern = rule.pattern.strip().lower()
    if not text or not pattern:
        return False
    if rule.account_type and rule.account_type != account_type:
        return False
    if rule.direction == "out" and not (amount is not None and amount < 0):
        return False
    if rule.direction == "in" and not (amount is not None and amount > 0):
        return False
    if rule.match == "exact":
        return text == pattern
    if rule.match == "prefix":
        return text.startswith(pattern)
    return pattern in text


def apply_rules(db: Session, transaction_ids: Iterable[str] | None = None, *, rederive: bool = False) -> int:
    """Categorize uncategorized transactions (and, with rederive, rule-set ones). Does not commit."""
    rules = _ordered(db.execute(select(CategoryRule)).scalars().all())
    if not rules:
        return 0
    stmt = select(Transaction)
    if transaction_ids is not None:
        ids = list(transaction_ids)
        if not ids:
            return 0
        stmt = stmt.where(Transaction.id.in_(ids))
    uncategorized = or_(Transaction.category.is_(None), Transaction.category == "")
    if rederive:
        stmt = stmt.where(or_(uncategorized, Transaction.category_source.like("rule:%")))
    else:
        stmt = stmt.where(uncategorized)
    account_types = dict(db.execute(select(Account.id, Account.account_type)).all())
    changed = 0
    for txn in db.execute(stmt).scalars():
        if (txn.category_source or "") in PROTECTED_SOURCES:
            continue
        amount = float(txn.amount) if txn.amount is not None else None
        for rule in rules:
            if rule_matches(rule, txn.merchant, account_types.get(txn.account_id), amount):
                if (txn.category, txn.category_group) != (rule.category, rule.category_group):
                    changed += 1
                txn.category, txn.category_group = rule.category, rule.category_group
                txn.category_source = f"rule:{rule.source}"
                break
    db.flush()
    return changed


def set_category(db: Session, txn: Transaction, category: str | None, category_group: str | None, source: str = "manual") -> None:
    """The owner's (or a receipt's) category; rules never overwrite it."""
    txn.category, txn.category_group = category, category_group
    txn.category_source = source if category else None


def category_options(db: Session) -> list[tuple[str, str | None]]:
    """Every (category, group) in use by a transaction or a rule, sorted by group then name."""
    pairs = set(db.execute(select(Transaction.category, Transaction.category_group).where(Transaction.category.is_not(None))).all())
    pairs |= set(db.execute(select(CategoryRule.category, CategoryRule.category_group)).all())
    return sorted(pairs, key=lambda p: ((p[1] or ""), p[0]))


def add_rule(db: Session, *, pattern: str, match: str, category: str, category_group: str,
             account_type: str | None = None, direction: str | None = None, source: str = "manual",
             note: str | None = None, priority: int = 10) -> tuple[CategoryRule, int]:
    """Create a rule and re-derive every rule-set or uncategorized transaction. Does not commit."""
    if match not in _MATCH_ORDER:
        raise ValueError(f"match must be one of {sorted(_MATCH_ORDER)}")
    rule = CategoryRule(pattern=pattern.strip(), match=match, category=category.strip(),
                        category_group=category_group.strip(), account_type=account_type,
                        direction=direction, source=source, note=note, priority=priority)
    db.add(rule)
    db.flush()
    return rule, apply_rules(db, rederive=True)


def update_transaction(db: Session, txn: Transaction, changes: dict) -> Transaction:
    """Apply edits from the owner. A category chosen by hand is marked manual so rules leave it alone."""
    category_changed = "category" in changes or "category_group" in changes
    for key, value in changes.items():
        setattr(txn, key, value)
    if category_changed:
        txn.category_source = "manual" if txn.category else None
    db.flush()
    return txn
