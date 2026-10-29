"""SimpleFIN Bridge provider.

SimpleFIN: a one-time setup token (base64 of a claim URL) is POSTed once to
obtain a permanent access URL with embedded basic-auth credentials. One
endpoint, GET {access_url}/accounts, returns every account with its balance
and recent transactions. The access URL is the credential and is stored
encrypted (services/crypto.py).
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import aiohttp
from sqlalchemy.orm import Session

from app.models.simplefin_link import SimpleFinAccountConfig, SimpleFinLink
from app.services.crypto import decrypt_secret
from app.services.providers.base import (
    AccountSyncConfig,
    ProviderAccount,
    ProviderConnection,
    ProviderError,
    ProviderSnapshot,
    ProviderTransaction,
)

logger = logging.getLogger("tallied.providers.simplefin")

HISTORY_DAYS = 45
USER_AGENT = "Tallied/1.0"


def classify_kind(name: str, has_holdings: bool) -> str:
    """Best-effort account kind from a SimpleFIN account (it carries no type field).

    Used once, at connect time, to pre-fill the editable type on the account config.
    """
    if has_holdings:
        return "investment"
    n = (name or "").lower()
    if "401" in n or "ira" in n or "retirement" in n:
        return "retirement"
    if "mortgage" in n:
        return "mortgage"
    if "loan" in n:
        return "loan"
    if any(k in n for k in ("credit", "visa", "mastercard", "amex", "card")):
        return "credit_card"
    if "saving" in n or "money market" in n or "hysa" in n:
        return "savings"
    return "checking"


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def normalize(raw: dict) -> ProviderSnapshot:
    """Turn the /accounts payload into a ProviderSnapshot. Pure; unit-tested."""
    accounts: list[ProviderAccount] = []
    for acct in raw.get("accounts", []) or []:
        org = acct.get("org") or {}
        institution = org.get("name", "") if isinstance(org, dict) else ""
        balance_date = None
        if acct.get("balance-date"):
            try:
                balance_date = datetime.fromtimestamp(int(acct["balance-date"]), tz=timezone.utc).date()
            except (ValueError, TypeError, OSError):
                balance_date = None
        txns: list[ProviderTransaction] = []
        seen: set[str] = set()
        for t in acct.get("transactions", []) or []:
            tid = str(t.get("id", "") or "")
            posted = t.get("posted") or t.get("transacted_at")
            amount = _decimal(t.get("amount"))
            if not tid or tid in seen or not posted or amount is None:
                continue
            try:
                tdate = datetime.fromtimestamp(int(posted), tz=timezone.utc).date()
            except (ValueError, TypeError, OSError):
                continue
            seen.add(tid)
            txns.append(ProviderTransaction(
                id=tid,
                date=tdate,
                amount=amount,
                merchant=(t.get("payee") or t.get("description") or "").strip(),
                pending=bool(t.get("pending")),
            ))
        name = acct.get("name", "Unknown") or "Unknown"
        accounts.append(ProviderAccount(
            id=str(acct.get("id", "")),
            name=name,
            institution=institution,
            kind=classify_kind(name, bool(acct.get("holdings"))),
            balance=_decimal(acct.get("balance")),
            balance_date=balance_date,
            transactions=txns,
        ))
    warnings = [str(e) for e in (raw.get("errors") or [])]
    return ProviderSnapshot(accounts=accounts, warnings=warnings)


class SimpleFinProvider:
    name = "simplefin"
    display_name = "SimpleFIN"

    # ── credential lifecycle ──────────────────────────────────────────────

    @staticmethod
    def decode_setup_token(setup_token: str) -> str:
        raw = setup_token.strip()
        try:
            claim_url = base64.b64decode(raw).decode().strip()
        except Exception:
            raise ProviderError("Setup token is not valid base64. Paste the entire token from SimpleFIN.", status_code=400)
        if not claim_url.startswith("https://"):
            raise ProviderError("Decoded setup token doesn't look like a claim URL.", status_code=400)
        return claim_url

    async def claim_setup_token(self, setup_token: str) -> str:
        """Exchange a single-use setup token for the permanent access URL."""
        claim_url = self.decode_setup_token(setup_token)
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(claim_url, headers={"Content-Length": "0", "User-Agent": USER_AGENT}) as r:
                body = (await r.text()).strip()
                if r.status != 200:
                    raise ProviderError(f"SimpleFIN rejected the setup token ({r.status}): {body[:200]}", status_code=400)
                if not body.startswith("https://"):
                    raise ProviderError("SimpleFIN response wasn't an access URL; the token may already be used.", status_code=400)
                return body

    # ── data ──────────────────────────────────────────────────────────────

    async def fetch(self, credential: str) -> ProviderSnapshot:
        p = urlparse(credential)
        if not p.username or not p.password:
            raise ProviderError("Stored access URL is missing credentials. Reconnect SimpleFIN.", status_code=401)
        end = int(datetime.now(timezone.utc).timestamp())
        start = end - HISTORY_DAYS * 24 * 3600
        url = f"{p.scheme}://{p.hostname}{p.path}/accounts?start-date={start}&end-date={end}&pending=1"
        auth = aiohttp.BasicAuth(p.username, p.password)
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(url, auth=auth, headers={"User-Agent": USER_AGENT}) as r:
                if r.status in (401, 403):
                    raise ProviderError("SimpleFIN access URL was revoked. Re-claim a fresh setup token in Settings.", status_code=401)
                if r.status >= 400:
                    raise ProviderError(f"SimpleFIN returned HTTP {r.status}", status_code=502)
                raw = await r.json()
        return normalize(raw)

    # ── stored connection ─────────────────────────────────────────────────

    def get_connection(self, db: Session) -> ProviderConnection | None:
        link = db.query(SimpleFinLink).first()
        if not link:
            return None
        configs = {
            c.simplefin_account_id: AccountSyncConfig(
                external_id=c.simplefin_account_id,
                account_name=c.account_name,
                institution=c.institution or "",
                account_type=c.account_type,
                sync_balances=bool(c.sync_balances),
                sync_transactions=bool(c.sync_transactions),
                local_account_id=c.local_account_id,
                row=c,
            )
            for c in db.query(SimpleFinAccountConfig).filter(SimpleFinAccountConfig.simplefin_link_id == link.id).all()
        }
        return ProviderConnection(credential=decrypt_secret(link.access_url), configs=configs, row=link)
