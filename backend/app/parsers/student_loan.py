from datetime import date, datetime

from app.parsers.base import BaseParser, ParseResult


class StudentLoanParser(BaseParser):
    def can_handle(self, source: str) -> bool:
        return source.lower() in ("student_loan", "student_loans", "studentloan")

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

        loan_count = 0
        snapshot_count = 0
        total_balance = 0.0

        loans = raw_data.get("loans", [])
        if not loans:
            errors.append("No loans found in raw data")

        for i, loan in enumerate(loans):
            try:
                servicer = loan.get("servicer", "Unknown")
                balance = loan.get("balance")

                if balance is None:
                    errors.append(f"Loan {i} missing balance, skipped")
                    continue

                # Generate a stable account id from servicer name
                account_id = f"student-loan-{servicer.lower().replace(' ', '-')}"

                # Ensure the account exists
                records.append(
                    {
                        "table": "accounts",
                        "data": {
                            "id": account_id,
                            "name": f"Student Loan ({servicer})",
                            "institution": servicer,
                            "account_type": "loan_student",
                            "display_group": "Other Loans",
                            "include_in_nw": True,
                            "is_active": True,
                        },
                    }
                )

                # Balance snapshot — loans are liabilities so store as negative
                records.append(
                    {
                        "table": "balance_snapshots",
                        "data": {
                            "account_id": account_id,
                            "snapshot_date": today.isoformat(),
                            "balance": -abs(float(balance)),
                            "source": "student_loan",
                        },
                    }
                )

                total_balance += abs(float(balance))
                loan_count += 1
                snapshot_count += 1

            except Exception as e:
                errors.append(f"Error parsing loan {i}: {e}")

        summary = {
            "loans": loan_count,
            "balance_snapshots": snapshot_count,
            "total_balance": total_balance,
        }

        return ParseResult(records=records, summary=summary, errors=errors)
