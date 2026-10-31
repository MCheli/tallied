"""Fetch current stock prices and price history from Yahoo Finance (cached)."""
import json
import logging
import re
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.investment import StockPrice

logger = logging.getLogger("tallied.stock_price")


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


RANGE_DAYS = {"1mo": 31, "3mo": 92, "6mo": 183, "1y": 366, "2y": 731, "5y": 1827, "10y": 3653, "max": None}


def price_series(db: Session, symbol: str, range_: str = "5y", today: date | None = None) -> list[dict]:
    """Closing prices for charts and backfills: Yahoo's weekly closes for the long history, with every price
    stored in `stock_prices` taking precedence on its day, so the series ends on the same price the rest of
    the app uses. The demo uses stored prices only. Raises ValueError on a bad symbol or range, or when
    Yahoo fails and nothing is stored."""
    from app.config import settings

    symbol = symbol.upper()
    if not valid_symbol(symbol):
        raise ValueError(f"Invalid symbol: {symbol!r}")
    if range_ not in RANGE_DAYS:
        raise ValueError(f"Invalid range: {range_!r}")
    today = today or date.today()
    q = select(StockPrice).where(StockPrice.symbol == symbol, StockPrice.price_date <= today)
    if RANGE_DAYS[range_] is not None:
        q = q.where(StockPrice.price_date >= today - timedelta(days=RANGE_DAYS[range_]))
    stored = db.execute(q).scalars().all()

    points: dict[str, float] = {}
    yahoo_error: ValueError | None = None
    if not settings.demo_mode:
        try:
            points.update({p["date"]: p["price"] for p in fetch_price_history(symbol, range_)})
        except ValueError as e:
            yahoo_error = e
            logger.warning("Price history for %s: Yahoo unavailable, stored prices only (%s)", symbol, e)
    points.update({r.price_date.isoformat(): round(float(r.close_price), 2) for r in stored})
    if not points and yahoo_error is not None:
        raise yahoo_error
    return [{"date": d, "price": points[d]} for d in sorted(points) if d <= today.isoformat()]


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
