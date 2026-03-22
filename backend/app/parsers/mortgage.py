from datetime import date, datetime

from app.parsers.base import BaseParser, ParseResult

# Stable synthetic IDs for the mortgage-related accounts
MORTGAGE_ACCOUNT_ID = "mortgage-primary"
PROPERTY_ACCOUNT_ID = "property-primary"


class MortgageParser(BaseParser):
    def can_handle(self, source: str) -> bool:
        return source.lower() in ("mortgage", "mortgage_servicer")

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

        current_balance = raw_data.get("currentBalance")
        interest_rate = raw_data.get("interestRate")
        monthly_payment = raw_data.get("monthlyPayment")
        origination_date = raw_data.get("originationDate")
        original_amount = raw_data.get("originalAmount")
        payoff_date = raw_data.get("payoffDate")
        property_value = raw_data.get("propertyValue")

        # Validate required fields for mortgage record
        if interest_rate is None or monthly_payment is None:
            errors.append("Missing interestRate or monthlyPayment; mortgage record may be incomplete")

        # Ensure the mortgage account exists
        records.append(
            {
                "table": "accounts",
                "data": {
                    "id": MORTGAGE_ACCOUNT_ID,
                    "name": "Primary Mortgage",
                    "institution": raw_data.get("servicer"),
                    "account_type": "loan_mortgage",
                    "display_group": "Other Loans",
                    "include_in_nw": True,
                    "is_active": True,
                },
            }
        )

        # Mortgage detail record
        mortgage_data: dict = {
            "account_id": MORTGAGE_ACCOUNT_ID,
            "rate": interest_rate,
            "monthly_payment": monthly_payment,
        }
        if origination_date:
            mortgage_data["origination_date"] = origination_date
        if original_amount is not None:
            mortgage_data["original_amount"] = float(original_amount)
        if payoff_date:
            mortgage_data["original_payoff_date"] = payoff_date
        if current_balance is not None:
            mortgage_data["current_balance"] = float(current_balance)

        records.append({"table": "mortgages", "data": mortgage_data})

        # Balance snapshot — mortgage is a liability so store as negative
        if current_balance is not None:
            records.append(
                {
                    "table": "balance_snapshots",
                    "data": {
                        "account_id": MORTGAGE_ACCOUNT_ID,
                        "snapshot_date": today.isoformat(),
                        "balance": -abs(float(current_balance)),
                        "source": "mortgage",
                    },
                }
            )

        # Property valuation
        if property_value is not None:
            # Ensure the property account exists
            records.append(
                {
                    "table": "accounts",
                    "data": {
                        "id": PROPERTY_ACCOUNT_ID,
                        "name": "Primary Residence",
                        "account_type": "real_estate",
                        "display_group": "Home Equity",
                        "include_in_nw": True,
                        "is_active": True,
                    },
                }
            )

            records.append(
                {
                    "table": "property_valuations",
                    "data": {
                        "account_id": PROPERTY_ACCOUNT_ID,
                        "valuation_date": today.isoformat(),
                        "value": float(property_value),
                        "source": "mortgage",
                    },
                }
            )

        summary = {
            "current_balance": current_balance,
            "interest_rate": interest_rate,
            "monthly_payment": monthly_payment,
            "property_value": property_value,
        }

        return ParseResult(records=records, summary=summary, errors=errors)
