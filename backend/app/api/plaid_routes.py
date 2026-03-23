"""
Plaid integration endpoints.

Setup:
1. Create a Plaid account at https://dashboard.plaid.com
2. Get your client_id and secret from the Plaid dashboard
3. Set env vars: FINANCE_PLAID_CLIENT_ID and FINANCE_PLAID_SECRET
4. Use sandbox credentials for development/testing (no real bank connections needed)
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.products import Products
from plaid.model.country_code import CountryCode

from app.config import settings
from app.dependencies import get_tenant_db
from app.models.plaid_link import PlaidLink
from app.models.transaction import Transaction
from app.models.balance import BalanceSnapshot
from app.models.account import Account
from decimal import Decimal

router = APIRouter(prefix="/plaid", tags=["plaid"])

# Map Plaid's SCREAMING_SNAKE categories to readable names
PLAID_CATEGORY_MAP = {
    "INCOME": "Paychecks",
    "TRANSFER_IN": "Transfer",
    "TRANSFER_OUT": "Transfer",
    "LOAN_PAYMENTS": "Loan Payment",
    "BANK_FEES": "Fees & Charges",
    "ENTERTAINMENT": "Entertainment & Recreation",
    "FOOD_AND_DRINK": "Restaurants & Bars",
    "GENERAL_MERCHANDISE": "Shopping",
    "GENERAL_SERVICES": "Shopping",
    "GOVERNMENT_AND_NON_PROFIT": "Taxes",
    "HOME_IMPROVEMENT": "Home Improvement",
    "MEDICAL": "Medical",
    "PERSONAL_CARE": "Personal",
    "RENT_AND_UTILITIES": "Bills & Utilities",
    "TRANSPORTATION": "Auto & Transport",
    "TRAVEL": "Travel",
}


def _normalize_plaid_category(raw: str | None) -> str:
    if not raw:
        return "Uncategorized"
    return PLAID_CATEGORY_MAP.get(raw, raw.replace("_", " ").title())


def _get_plaid_client() -> plaid_api.PlaidApi:
    configuration = plaid.Configuration(
        host=plaid.Environment.Sandbox,
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


@router.get("/link-token")
def create_link_token():
    """Generate a Plaid Link token to initiate the account connection flow."""
    client = _get_plaid_client()
    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="Personal Finance",
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id="local-user"),
    )
    try:
        response = client.link_token_create(request)
        return {"link_token": response["link_token"]}
    except plaid.ApiException as e:
        raise HTTPException(status_code=502, detail=str(e))


class ExchangeRequest(BaseModel):
    public_token: str
    institution_name: str


@router.post("/exchange")
def exchange_public_token(body: ExchangeRequest, db: Session = Depends(get_tenant_db)):
    """Exchange a Plaid public token for a permanent access token and store the link."""
    client = _get_plaid_client()
    try:
        exchange_response = client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=body.public_token)
        )
    except plaid.ApiException as e:
        raise HTTPException(status_code=502, detail=str(e))

    access_token = exchange_response["access_token"]
    item_id = exchange_response["item_id"]

    existing = db.query(PlaidLink).filter(PlaidLink.item_id == item_id).first()
    if existing:
        existing.access_token = access_token
        existing.institution_name = body.institution_name
        db.commit()
        return {"status": "updated", "item_id": item_id}

    link = PlaidLink(
        id=str(uuid.uuid4()),
        item_id=item_id,
        access_token=access_token,
        institution_name=body.institution_name,
    )
    db.add(link)
    db.commit()
    return {"status": "created", "item_id": item_id}


@router.post("/sync")
def sync_transactions(db: Session = Depends(get_tenant_db)):
    """Sync transactions for all linked Plaid institutions."""
    client = _get_plaid_client()
    links = db.query(PlaidLink).all()

    if not links:
        return {"synced": 0, "links_processed": 0, "detail": "No Plaid links found. Connect an institution first via /api/plaid/link-token."}

    total_added = 0
    total_modified = 0
    total_removed = 0
    results = []

    for link in links:
        added_count = 0
        modified_count = 0
        removed_count = 0
        cursor = link.cursor

        has_more = True
        while has_more:
            try:
                req_kwargs = {"access_token": link.access_token}
                if cursor:
                    req_kwargs["cursor"] = cursor
                response = client.transactions_sync(TransactionsSyncRequest(**req_kwargs))
            except plaid.ApiException as e:
                results.append({"institution": link.institution_name, "error": str(e)})
                break

            for txn in response["added"]:
                plaid_id = f"plaid-{txn['transaction_id']}"
                if db.query(Transaction).filter(Transaction.id == plaid_id).first():
                    continue

                # Plaid: positive = money leaving account; our model: negative = expense
                our_amount = -txn["amount"]

                raw_date = txn.get("date")
                txn_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date

                merchant = txn.get("merchant_name") or txn.get("name") or ""

                pfc = txn.get("personal_finance_category")
                raw_category = (
                    pfc.get("primary") if isinstance(pfc, dict)
                    else getattr(pfc, "primary", None)
                )

                db.add(Transaction(
                    id=plaid_id,
                    date=txn_date,
                    amount=our_amount,
                    merchant=merchant,
                    category=_normalize_plaid_category(raw_category),
                    source="plaid",
                ))
                added_count += 1

            for txn in response["modified"]:
                plaid_id = f"plaid-{txn['transaction_id']}"
                existing = db.query(Transaction).filter(Transaction.id == plaid_id).first()
                if not existing:
                    continue
                existing.amount = -txn["amount"]
                raw_date = txn.get("date")
                existing.date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date
                existing.merchant = txn.get("merchant_name") or txn.get("name") or ""
                pfc = txn.get("personal_finance_category")
                raw_cat = (
                    pfc.get("primary") if isinstance(pfc, dict)
                    else getattr(pfc, "primary", None)
                )
                existing.category = _normalize_plaid_category(raw_cat)
                modified_count += 1

            for removal in response["removed"]:
                plaid_id = f"plaid-{removal['transaction_id']}"
                existing = db.query(Transaction).filter(Transaction.id == plaid_id).first()
                if existing:
                    db.delete(existing)
                    removed_count += 1

            cursor = response["next_cursor"]
            has_more = response["has_more"]

        link.cursor = cursor
        db.commit()

        total_added += added_count
        total_modified += modified_count
        total_removed += removed_count
        results.append({
            "institution": link.institution_name,
            "added": added_count,
            "modified": modified_count,
            "removed": removed_count,
        })

    return {
        "links_processed": len(links),
        "total_added": total_added,
        "total_modified": total_modified,
        "total_removed": total_removed,
        "details": results,
    }


@router.get("/links")
def list_links(db: Session = Depends(get_tenant_db)):
    """List all connected Plaid institutions."""
    links = db.query(PlaidLink).all()
    return [
        {
            "id": l.id,
            "institution_name": l.institution_name,
            "institution_id": l.institution_id,
            "has_cursor": l.cursor is not None,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in links
    ]


@router.post("/sync-balances")
def sync_balances(db: Session = Depends(get_tenant_db)):
    """Fetch current account balances from all linked Plaid institutions."""
    client = _get_plaid_client()
    links = db.query(PlaidLink).all()

    if not links:
        return {"accounts": [], "detail": "No Plaid links found"}

    all_accounts = []
    today = date.today()

    for link in links:
        try:
            response = client.accounts_balance_get(
                AccountsBalanceGetRequest(access_token=link.access_token)
            )
        except plaid.ApiException as e:
            all_accounts.append({"institution": link.institution_name, "error": str(e)})
            continue

        for acct in response["accounts"]:
            acct_name = acct.get("name", "")
            acct_mask = acct.get("mask", "")
            acct_type = acct.get("type", "")
            acct_subtype = acct.get("subtype", "")
            balance_current = acct.get("balances", {}).get("current")
            balance_available = acct.get("balances", {}).get("available")

            # Map Plaid account type to our display_group
            display_group = "Cash"
            if str(acct_type) in ("investment", "brokerage"):
                display_group = "Investments"
            elif str(acct_type) == "credit":
                display_group = "Credit Cards"
            elif str(acct_type) == "loan":
                display_group = "Other Loans"

            our_type = "cash"
            if str(acct_subtype) == "checking":
                our_type = "cash"
            elif str(acct_subtype) == "savings":
                our_type = "cash"
            elif str(acct_subtype) == "credit card":
                our_type = "credit_card"

            # Find or create matching local account
            plaid_acct_id = acct.get("account_id", "")
            local_id = f"plaid-{plaid_acct_id}"

            local_acct = db.query(Account).filter(Account.id == local_id).first()
            if not local_acct:
                local_acct = Account(
                    id=local_id,
                    name=f"{acct_name} (...{acct_mask})" if acct_mask else acct_name,
                    institution=link.institution_name,
                    account_type=our_type,
                    display_group=display_group,
                    include_in_nw=True,
                )
                db.add(local_acct)
                db.flush()

            # Add balance snapshot
            if balance_current is not None:
                existing = db.query(BalanceSnapshot).filter(
                    BalanceSnapshot.account_id == local_id,
                    BalanceSnapshot.snapshot_date == today,
                    BalanceSnapshot.source == "plaid",
                ).first()

                bal_value = Decimal(str(balance_current))
                if existing:
                    existing.balance = bal_value
                else:
                    db.add(BalanceSnapshot(
                        account_id=local_id,
                        snapshot_date=today,
                        balance=bal_value,
                        source="plaid",
                    ))

            all_accounts.append({
                "name": acct_name,
                "mask": acct_mask,
                "type": str(acct_type),
                "subtype": str(acct_subtype),
                "balance_current": balance_current,
                "balance_available": balance_available,
                "institution": link.institution_name,
                "local_account_id": local_id,
            })

    db.commit()
    return {"accounts": all_accounts, "synced": len(all_accounts)}
