"""Email receipt parsing service — resolves forwarding email, parses with Claude, creates transactions."""
import json
import uuid
from datetime import date
from decimal import Decimal

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.email_forwarding_address import EmailForwardingAddress
from app.models.email_receipt import EmailReceipt
from app.models.transaction import Transaction


RECEIPT_PARSE_PROMPT = """You are parsing a forwarded email receipt or order confirmation.
Extract the transaction details and return ONLY valid JSON (no markdown, no explanation):

{
  "merchant": "Store name",
  "amount": 45.99,
  "date": "YYYY-MM-DD",
  "category": "Shopping",
  "items": [{"name": "Item name", "qty": 1, "price": 12.99}],
  "tax": 3.45,
  "shipping": 0.00,
  "order_id": "order reference if present or null",
  "is_refund": false
}

Category should be one of: Shopping, Restaurants & Bars, Entertainment & Recreation,
Bills & Utilities, Auto & Transport, Travel, Medical, Personal, Home Improvement,
Groceries, Subscriptions, Transfer, Uncategorized.

For refunds/returns, set is_refund to true and amount should be the refund amount (positive number).
If you cannot parse a valid receipt from the email, return: {"error": "reason"}"""


def resolve_forwarding_email(forwarded_by: str, db: Session) -> EmailForwardingAddress | None:
    """Look up a forwarding email address to find the user/tenant."""
    return db.execute(
        select(EmailForwardingAddress).where(
            EmailForwardingAddress.email == forwarded_by.lower().strip(),
            EmailForwardingAddress.is_active.is_(True),
        )
    ).scalar_one_or_none()


def parse_receipt_with_ai(subject: str, body: str, from_email: str) -> dict:
    """Call Claude to extract transaction data from an email receipt."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    email_content = f"From: {from_email}\nSubject: {subject}\n\n{body}"

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": f"{RECEIPT_PARSE_PROMPT}\n\n---\n\n{email_content}"}
        ],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    return json.loads(raw)


def create_transaction_from_receipt(db: Session, parsed: dict, receipt: EmailReceipt) -> Transaction:
    """Create a Transaction record from parsed receipt data."""
    amount = Decimal(str(parsed["amount"]))
    if parsed.get("tax"):
        amount += Decimal(str(parsed["tax"]))
    if parsed.get("shipping"):
        amount += Decimal(str(parsed["shipping"]))

    # Refunds are positive (money coming in), purchases are negative (money going out)
    if not parsed.get("is_refund"):
        amount = -amount

    txn_date = date.fromisoformat(parsed["date"]) if parsed.get("date") else date.today()

    items_summary = ""
    if parsed.get("items"):
        items_summary = ", ".join(item["name"] for item in parsed["items"][:5])

    notes_parts = []
    if parsed.get("order_id"):
        notes_parts.append(f"Order: {parsed['order_id']}")
    if items_summary:
        notes_parts.append(items_summary)
    notes_parts.append(f"email_receipt_id:{receipt.id}")

    txn = Transaction(
        id=f"email-{uuid.uuid4().hex[:12]}",
        date=txn_date,
        amount=amount,
        merchant=parsed.get("merchant", "Unknown"),
        category=parsed.get("category", "Uncategorized"),
        source="email_receipt",
        notes=" | ".join(notes_parts),
    )
    db.add(txn)
    return txn
