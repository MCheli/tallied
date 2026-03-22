"""Fetch current stock prices from Yahoo Finance."""
import json
import urllib.request
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.investment import StockPrice


def fetch_price(symbol: str) -> Optional[float]:
    """Get the current market price for a stock symbol via Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception:
        return None


def get_or_fetch_price(db: Session, symbol: str) -> Optional[float]:
    """Get today's Yahoo price from DB cache, or fetch live and cache it."""
    from sqlalchemy import select, and_
    today = date.today()

    # Check cache — only trust yahoo source
    cached = db.execute(
        select(StockPrice).where(
            and_(
                StockPrice.symbol == symbol,
                StockPrice.price_date == today,
                StockPrice.source == "yahoo",
            )
        )
    ).scalar_one_or_none()

    if cached:
        return float(cached.close_price)

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

    # Delete any existing entries for today (seed data, stale cache, etc.)
    old = db.execute(
        select(StockPrice).where(
            and_(
                StockPrice.symbol == symbol,
                StockPrice.price_date == today,
            )
        )
    ).scalars().all()
    for o in old:
        db.delete(o)
    db.flush()

    # Insert fresh yahoo price for today
    db.add(StockPrice(
        symbol=symbol,
        price_date=today,
        close_price=Decimal(str(round(price, 2))),
        source="yahoo",
    ))
    db.commit()

    return price
