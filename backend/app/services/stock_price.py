"""Fetch current stock prices and price history from Yahoo Finance (cached)."""
import json
import re
import time
import urllib.request
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.investment import StockPrice


def fetch_price(symbol: str) -> float | None:
    """Get the current market price for a stock symbol via Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception:
        return None


SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^]{1,12}$")
HISTORY_TTL_SECONDS = 6 * 3600
_history_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}


def valid_symbol(symbol: str) -> bool:
    return bool(symbol) and bool(SYMBOL_RE.match(symbol.upper()))


def fetch_price_history(symbol: str, range_: str = "5y", interval: str = "1wk") -> list[dict]:
    """Weekly closes for `symbol`, cached in-process for six hours. Raises ValueError on a bad symbol or Yahoo error."""
    symbol = symbol.upper()
    if not valid_symbol(symbol):
        raise ValueError(f"Invalid symbol: {symbol!r}")
    if range_ not in ("1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"):
        raise ValueError(f"Invalid range: {range_!r}")
    key = (symbol, range_)
    cached = _history_cache.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < HISTORY_TTL_SECONDS:
        return cached[1]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=8)
        data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        closes = result["indicators"]["quote"][0].get("close") or []
    except Exception as exc:
        raise ValueError(f"Yahoo Finance error: {exc}") from exc
    points = [
        {"date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"), "price": round(close, 2)}
        for ts, close in zip(timestamps, closes) if close is not None
    ]
    _history_cache[key] = (now, points)
    return points


def get_or_fetch_price(db: Session, symbol: str) -> float | None:
    """Get today's Yahoo price from DB cache, or fetch live and cache it."""
    from sqlalchemy import and_, select
    today = date.today()

    # One row per (symbol, day). Any row for today, whatever its source (yahoo, seed,
    # manual), is today's price: the seed's quote stays stable for the day it was seeded.
    cached = db.execute(
        select(StockPrice).where(and_(StockPrice.symbol == symbol, StockPrice.price_date == today))
    ).scalar_one_or_none()

    if cached:
        return float(cached.close_price)

    from app.config import settings

    if settings.demo_mode:  # the demo's database is read-only; its prices come from the nightly seed
        row = db.execute(
            select(StockPrice).where(StockPrice.symbol == symbol).order_by(StockPrice.price_date.desc()).limit(1)
        ).scalar_one_or_none()
        return float(row.close_price) if row else None

    # Fetch live from Yahoo
    price = fetch_price(symbol)
    if price is None:
        # Fall back to most recent yahoo price
        row = db.execute(
            select(StockPrice)
            .where(StockPrice.symbol == symbol, StockPrice.source == "yahoo")
            .order_by(StockPrice.price_date.desc())
            .limit(1)
        ).scalar_one_or_none()
        return float(row.close_price) if row else None

    # Insert fresh yahoo price for today
    db.add(StockPrice(
        symbol=symbol,
        price_date=today,
        close_price=Decimal(str(round(price, 2))),
        source="yahoo",
    ))
    db.commit()

    return price
