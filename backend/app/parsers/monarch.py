from datetime import date, datetime

from app.parsers.base import BaseParser, ParseResult

# Monarch account type → our account_type enum
ACCOUNT_TYPE_MAP: dict[str, str] = {
    "checking": "cash",
    "savings": "cash",
    "brokerage": "investment_stock",
    "401k": "investment_401k",
    "ira": "investment_401k",
    "roth_ira": "investment_401k",
    "mortgage": "loan_mortgage",
    "student_loan": "loan_student",
    "credit_card": "credit_card",
    "real_estate": "real_estate",
}

# Our account_type → display_group
DISPLAY_GROUP_MAP: dict[str, str] = {
    "cash": "Cash",
    "investment_stock": "Investments",
    "investment_401k": "Investments",
    "loan_mortgage": "Other Loans",
    "loan_student": "Other Loans",
    "credit_card": "Credit Cards",
    "real_estate": "Home Equity",
}


class MonarchParser(BaseParser):
    def can_handle(self, source: str) -> bool:
        return source.lower() in ("monarch", "monarch_money")

    def parse(self, raw_data: dict | str) -> ParseResult:
        if isinstance(raw_data, str):
            import json

            try:
                raw_data = json.loads(raw_data)
            except (json.JSONDecodeError, TypeError) as e:
                return ParseResult(errors=[f"Invalid JSON: {e}"])

        records: list[dict] = []
        errors: list[str] = []
        today = date.today()

        account_count = 0
        snapshot_count = 0
        transaction_count = 0

        # Parse accounts
        for acct in raw_data.get("accounts", []):
            try:
                acct_id = acct.get("id")
                if not acct_id:
                    errors.append("Account missing id, skipped")
                    continue

                monarch_type = self._extract_account_type(acct)
                account_type = ACCOUNT_TYPE_MAP.get(monarch_type, "cash")
                display_group = DISPLAY_GROUP_MAP.get(account_type, "Cash")

                records.append(
                    {
                        "table": "accounts",
                        "data": {
                            "id": acct_id,
                            "name": acct.get("displayName", acct.get("name", "Unknown")),
                            "institution": self._extract_nested(acct, "institution", "name"),
                            "account_type": account_type,
                            "display_group": display_group,
                            "include_in_nw": True,
                            "is_active": acct.get("isActive", True),
                        },
                    }
                )
                account_count += 1

                # Create a balance snapshot from currentBalance
                balance = acct.get("currentBalance")
                if balance is not None:
                    records.append(
                        {
                            "table": "balance_snapshots",
                            "data": {
                                "account_id": acct_id,
                                "snapshot_date": today.isoformat(),
                                "balance": float(balance),
                                "source": "monarch",
                            },
                        }
                    )
                    snapshot_count += 1

            except Exception as e:
                errors.append(f"Error parsing account {acct.get('id', '?')}: {e}")

        # Parse transactions
        for txn in raw_data.get("transactions", []):
            try:
                txn_id = txn.get("id")
                if not txn_id:
                    errors.append("Transaction missing id, skipped")
                    continue

                txn_date = txn.get("date")
                if not txn_date:
                    errors.append(f"Transaction {txn_id} missing date, skipped")
                    continue

                records.append(
                    {
                        "table": "transactions",
                        "data": {
                            "id": txn_id,
                            "account_id": self._extract_nested(txn, "account", "id"),
                            "date": txn_date,
                            "amount": txn.get("amount"),
                            "merchant": self._extract_nested(txn, "merchant", "name"),
                            "category": self._extract_nested(txn, "category", "name"),
                            "category_group": self._extract_category_group(txn),
                            "is_recurring": txn.get("isRecurring", False),
                            "notes": txn.get("notes"),
                            "source": "monarch",
                        },
                    }
                )
                transaction_count += 1

            except Exception as e:
                errors.append(f"Error parsing transaction {txn.get('id', '?')}: {e}")

        summary = {
            "accounts": account_count,
            "balance_snapshots": snapshot_count,
            "transactions": transaction_count,
        }

        return ParseResult(records=records, summary=summary, errors=errors)

    @staticmethod
    def _extract_account_type(acct: dict) -> str:
        """Extract account type string from Monarch's nested structure."""
        type_obj = acct.get("type")
        if isinstance(type_obj, dict):
            return type_obj.get("name", "").lower().replace(" ", "_")
        if isinstance(type_obj, str):
            return type_obj.lower().replace(" ", "_")
        return ""

    @staticmethod
    def _extract_nested(obj: dict, key: str, subkey: str) -> str | None:
        """Safely extract a value from a nested dict like obj[key][subkey]."""
        nested = obj.get(key)
        if isinstance(nested, dict):
            return nested.get(subkey)
        return None

    @staticmethod
    def _extract_category_group(txn: dict) -> str | None:
        """Extract category group from Monarch's nested category.group.name."""
        category = txn.get("category")
        if isinstance(category, dict):
            group = category.get("group")
            if isinstance(group, dict):
                return group.get("name")
        return None
