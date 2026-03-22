import json
import logging
import traceback
from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.import_log import ImportLog
from app.models.account import Account
from app.models.balance import BalanceSnapshot
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


def preview_import(
    db: Session,
    source: str,
    capture_mode: str,
    raw_data: dict | list | str,
) -> dict:
    """Parse raw data and return preview without saving to DB."""
    raw_str = json.dumps(raw_data) if isinstance(raw_data, (dict, list)) else raw_data

    log = ImportLog(
        source=source,
        capture_mode=capture_mode,
        status="preview",
        raw_data=raw_str,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    try:
        parser = _get_parser(source)
        result = parser(db, raw_data, dry_run=True)

        records = result.get("records", [])
        summary = result.get("summary", {})

        # Build the preview with is_new/update status for each record
        preview_accounts = []
        preview_transactions = []
        preview_balance_snapshots = []

        new_accounts = 0
        updated_balances = 0

        for record in records:
            table = record["table"]
            row = record["data"]

            if table == "accounts":
                existing = db.get(Account, row["id"])
                is_new = existing is None
                if is_new:
                    new_accounts += 1
                preview_accounts.append({
                    "id": row["id"],
                    "name": row.get("name", "Unknown"),
                    "type": row.get("account_type", "unknown"),
                    "institution": row.get("institution"),
                    "is_new": is_new,
                })

            elif table == "balance_snapshots":
                snap_date = row.get("snapshot_date")
                if isinstance(snap_date, str):
                    snap_date = date_type.fromisoformat(snap_date)
                existing = db.execute(
                    select(BalanceSnapshot).where(
                        BalanceSnapshot.account_id == row["account_id"],
                        BalanceSnapshot.snapshot_date == snap_date,
                        BalanceSnapshot.source == row.get("source", source),
                    )
                ).scalar_one_or_none()
                is_new = existing is None
                if not is_new:
                    updated_balances += 1

                # Look up account name
                acct = db.get(Account, row["account_id"])
                acct_name = acct.name if acct else row["account_id"]

                preview_balance_snapshots.append({
                    "account": acct_name,
                    "account_id": row["account_id"],
                    "date": str(snap_date),
                    "balance": row.get("balance"),
                    "is_new": is_new,
                })

            elif table == "transactions":
                existing = db.get(Transaction, row["id"])
                is_new = existing is None
                preview_transactions.append({
                    "date": str(row.get("date", "")),
                    "merchant": row.get("merchant", "Unknown"),
                    "amount": row.get("amount"),
                    "category": row.get("category"),
                    "is_new": is_new,
                })

        preview = {
            "accounts": preview_accounts,
            "transactions": preview_transactions,
            "balance_snapshots": preview_balance_snapshots,
            "totals": {
                "accounts": len(preview_accounts),
                "transactions": len(preview_transactions),
                "balance_snapshots": len(preview_balance_snapshots),
                "new_accounts": new_accounts,
                "updated_balances": updated_balances,
            },
        }

        # Store parsed records in import_log so we can apply them later
        log.parsed_summary = json.dumps({
            "preview": preview,
            "records": records,
        })
        log.status = "preview"
        db.commit()
        db.refresh(log)

        return {
            "import_id": log.id,
            "status": "preview",
            "preview": preview,
        }

    except Exception as e:
        db.rollback()
        log = db.merge(log)
        log.status = "error"
        log.error_message = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        db.commit()
        raise


def confirm_import(db: Session, import_id: int) -> dict:
    """Apply the parsed records from a preview import."""
    log = db.get(ImportLog, import_id)
    if not log:
        raise ValueError(f"Import log {import_id} not found")
    if log.status != "preview":
        raise ValueError(f"Import {import_id} has status '{log.status}', expected 'preview'")
    if not log.parsed_summary:
        raise ValueError(f"Import {import_id} has no parsed data to apply")

    try:
        stored = json.loads(log.parsed_summary)
        records = stored.get("records", [])

        records_created = 0
        for record in records:
            table = record["table"]
            row = record["data"]

            if table == "accounts":
                existing = db.get(Account, row["id"])
                if not existing:
                    db.add(Account(**row))
                    records_created += 1

            elif table == "balance_snapshots":
                if isinstance(row.get("snapshot_date"), str):
                    row["snapshot_date"] = date_type.fromisoformat(row["snapshot_date"])
                existing = db.execute(
                    select(BalanceSnapshot).where(
                        BalanceSnapshot.account_id == row["account_id"],
                        BalanceSnapshot.snapshot_date == row["snapshot_date"],
                        BalanceSnapshot.source == row.get("source", "monarch"),
                    )
                ).scalar_one_or_none()
                if not existing:
                    db.add(BalanceSnapshot(**row))
                    records_created += 1

            elif table == "transactions":
                if isinstance(row.get("date"), str):
                    row["date"] = date_type.fromisoformat(row["date"])
                existing = db.get(Transaction, row["id"])
                if not existing:
                    db.add(Transaction(**row))
                    records_created += 1

        db.commit()

        log.status = "applied"
        log.records_created = records_created
        db.commit()
        db.refresh(log)

        return {
            "import_id": log.id,
            "status": "applied",
            "records_created": records_created,
        }

    except (ValueError, json.JSONDecodeError):
        raise
    except Exception as e:
        db.rollback()
        log = db.merge(log)
        log.status = "error"
        log.error_message = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        db.commit()
        raise


def reject_import(db: Session, import_id: int) -> dict:
    """Reject a previewed import — no data written."""
    log = db.get(ImportLog, import_id)
    if not log:
        raise ValueError(f"Import log {import_id} not found")
    if log.status != "preview":
        raise ValueError(f"Import {import_id} has status '{log.status}', expected 'preview'")

    log.status = "rejected"
    db.commit()
    db.refresh(log)

    return {
        "import_id": log.id,
        "status": "rejected",
    }


def process_import(
    db: Session,
    source: str,
    capture_mode: str,
    raw_data: dict | list | str,
) -> ImportLog:
    raw_str = json.dumps(raw_data) if isinstance(raw_data, (dict, list)) else raw_data

    log = ImportLog(
        source=source,
        capture_mode=capture_mode,
        status="received",
        raw_data=raw_str,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    try:
        parser = _get_parser(source)
        result = parser(db, raw_data)

        log.status = "applied"
        log.records_created = result.get("records_created", 0)
        log.parsed_summary = json.dumps(result.get("summary", {}))
        db.commit()

    except NotImplementedError as e:
        db.rollback()
        log = db.merge(log)
        log.status = "error"
        log.error_message = str(e)
        db.commit()

    except Exception as e:
        db.rollback()
        log = db.merge(log)
        log.status = "error"
        log.error_message = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        db.commit()

    db.refresh(log)
    return log


def _normalize_source(source: str) -> str:
    """Map hostnames and aliases to canonical parser names."""
    s = source.lower()
    if "monarchmoney" in s or s == "monarch":
        return "monarch"
    if "etrade" in s or "edwardjones" in s:
        return "etrade"
    if s in ("manual", "manual-paste"):
        return "manual"
    return s


def _get_parser(source: str):
    parsers = {
        "monarch": _parse_monarch,
        "etrade": _parse_etrade,
        "manual": _parse_manual,
    }
    normalized = _normalize_source(source)
    parser = parsers.get(normalized)
    if parser is None:
        return _parse_generic
    return parser


def _extract_from_intercepted(intercepted: list) -> dict:
    """Extract financial data from intercepted API response bodies.

    The extension captures [{url, method, body, ...}] — we need to dig into
    the 'body' field of each response to find accounts, transactions, etc.
    Handles both Monarch GraphQL and REST-style responses.
    """
    merged: dict[str, list] = {}

    for entry in intercepted:
        if not isinstance(entry, dict):
            continue
        body = entry.get("body")
        if not body or not isinstance(body, dict):
            continue

        # GraphQL responses have body.data.X — prefer that over body directly
        source_obj = body
        if isinstance(body.get("data"), dict):
            source_obj = body["data"]

        for key, val in source_obj.items():
            if isinstance(val, list) and len(val) > 0:
                if key not in merged:
                    merged[key] = []
                merged[key].extend(val)
            elif isinstance(val, dict):
                # One level deeper: body.data.portfolio.holdings
                for subkey, subval in val.items():
                    if isinstance(subval, list) and len(subval) > 0:
                        if subkey not in merged:
                            merged[subkey] = []
                        merged[subkey].extend(subval)

    return merged


def _parse_monarch(db: Session, raw_data: dict | list | str, dry_run: bool = False) -> dict:
    from app.parsers.monarch import MonarchParser

    data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data

    # If data is a list of intercepted API responses, extract financial data from bodies
    if isinstance(data, list):
        data = _extract_from_intercepted(data)

    parser = MonarchParser()
    result = parser.parse(data)

    if dry_run:
        return {"records": result.records, "summary": result.summary}

    records_created = 0
    for record in result.records:
        table = record["table"]
        row = record["data"]

        if table == "accounts":
            existing = db.get(Account, row["id"])
            if not existing:
                db.add(Account(**row))
                records_created += 1

        elif table == "balance_snapshots":
            if isinstance(row.get("snapshot_date"), str):
                row["snapshot_date"] = date_type.fromisoformat(row["snapshot_date"])
            existing = db.execute(
                select(BalanceSnapshot).where(
                    BalanceSnapshot.account_id == row["account_id"],
                    BalanceSnapshot.snapshot_date == row["snapshot_date"],
                    BalanceSnapshot.source == row.get("source", "monarch"),
                )
            ).scalar_one_or_none()
            if not existing:
                db.add(BalanceSnapshot(**row))
                records_created += 1

        elif table == "transactions":
            if isinstance(row.get("date"), str):
                row["date"] = date_type.fromisoformat(row["date"])
            existing = db.get(Transaction, row["id"])
            if not existing:
                db.add(Transaction(**row))
                records_created += 1

    db.commit()
    return {"records_created": records_created, "summary": result.summary}


def _parse_etrade(db: Session, raw_data: dict | list | str, dry_run: bool = False) -> dict:
    data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data

    if isinstance(data, list):
        data = _extract_from_intercepted(data)

    records = []
    summary = {"type": "etrade", "fields": list(data.keys()) if isinstance(data, dict) else []}

    # TODO: build records from E-Trade specific data structure
    # For now, just report what was found
    if isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, list):
                summary[f"{key}_count"] = len(val)

    if dry_run:
        return {"records": records, "summary": summary}

    return {"records_created": 0, "summary": summary}


def _parse_manual(db: Session, raw_data: dict | list | str, dry_run: bool = False) -> dict:
    data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data

    records_created = 0
    records = []
    summary = {"type": "manual"}

    if isinstance(data, dict):
        summary["fields"] = list(data.keys())

        if "balances" in data:
            for entry in data["balances"]:
                acct_id = entry["account_id"]
                snap_date = date_type.fromisoformat(entry["date"])

                records.append({
                    "table": "balance_snapshots",
                    "data": {
                        "account_id": acct_id,
                        "snapshot_date": snap_date.isoformat(),
                        "balance": entry["balance"],
                        "source": "manual",
                    },
                })

                if dry_run:
                    continue

                existing = db.execute(
                    select(BalanceSnapshot).where(
                        BalanceSnapshot.account_id == acct_id,
                        BalanceSnapshot.snapshot_date == snap_date,
                        BalanceSnapshot.source == "manual",
                    )
                ).scalar_one_or_none()
                if existing:
                    existing.balance = entry["balance"]
                else:
                    db.add(BalanceSnapshot(
                        account_id=acct_id,
                        snapshot_date=snap_date,
                        balance=entry["balance"],
                        source="manual",
                    ))
                records_created += 1

            if not dry_run:
                db.commit()

    if dry_run:
        return {"records": records, "summary": summary}

    return {"records_created": records_created, "summary": summary}


def _parse_generic(db: Session, raw_data: dict | list | str, dry_run: bool = False) -> dict:
    """Generic parser for unknown sources — extracts what it can from intercepted API data."""
    data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data

    if isinstance(data, list):
        data = _extract_from_intercepted(data)

    records = []
    summary = {"type": "generic"}

    if isinstance(data, dict):
        summary["fields"] = list(data.keys())
        for key, val in data.items():
            if isinstance(val, list):
                summary[f"{key}_count"] = len(val)

    if dry_run:
        return {"records": records, "summary": summary}

    return {"records_created": 0, "summary": summary}
