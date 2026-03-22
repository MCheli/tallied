"""
Load RSU grant and vest data from E-Trade spreadsheet exports.

Reads:
  - etrade_holdingsbytype_expanded.xlsx  (Restricted Stock sheet)
    → Grant rows, Vest Schedule rows, Tax Withholding rows, Sellable Shares rows
  - etrade_holdingsbystatus_expanded.xlsx (Sellable sheet)
    → Cost basis per share, tax status (Long/Short Term)

Writes to: rsu_grants, vest_events, stock_prices
"""
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.models.investment import RSUGrant, VestEvent, StockPrice


def _parse_date(val) -> date | None:
    if pd.isna(val) or val is None:
        return None
    s = str(val).strip()
    for fmt in ("%d-%b-%Y", "%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _safe_int(val) -> int | None:
    if pd.isna(val) or val is None:
        return None
    return int(float(val))


def _safe_decimal(val) -> Decimal | None:
    if pd.isna(val) or val is None:
        return None
    try:
        return Decimal(str(float(val))).quantize(Decimal("0.01"))
    except Exception:
        return None


def load_etrade_rsu(db: Session, data_dir: Path) -> dict:
    """Load RSU data from E-Trade exports into the database.

    Returns summary dict with counts.
    """
    by_type_path = data_dir / "etrade_holdingsbytype_expanded.xlsx"
    by_status_path = data_dir / "etrade_holdingsbystatus_expanded.xlsx"

    if not by_type_path.exists():
        return {"error": f"File not found: {by_type_path}"}

    df = pd.read_excel(by_type_path, sheet_name="Restricted Stock")
    grant_rows = df[df["Record Type"] == "Grant"]
    vest_rows = df[df["Record Type"] == "Vest Schedule"]
    tax_rows = df[df["Record Type"] == "Tax Withholding"]

    # Build cost basis lookup from sellable shares in by-status export
    # Key: (grant_number, vest_period) → cost_basis_per_share
    cost_basis_map: dict[tuple[int, int], Decimal] = {}
    tax_status_map: dict[tuple[int, int], str] = {}  # Long Term / Short Term
    if by_status_path.exists():
        sellable_df = pd.read_excel(by_status_path, sheet_name="Sellable")
        for _, row in sellable_df.iterrows():
            gn = _safe_int(row.get("Grant Number"))
            vp = _safe_int(row.get("Vest Period"))
            cb = _safe_decimal(row.get("Est. Cost Basis (per share):"))
            ts = row.get("Tax Status.1") or row.get("Tax Status")
            if gn is not None and vp is not None:
                if cb is not None:
                    cost_basis_map[(gn, vp)] = cb
                if pd.notna(ts):
                    tax_status_map[(gn, vp)] = str(ts)

    # Also compute cost basis from vest events: taxable_gain / shares = FMV at vest
    # Group tax withholding by (grant_number, vest_period) to get taxable gain
    vest_fmv_from_tax: dict[tuple[int, int], Decimal] = {}
    vest_tax_totals: dict[tuple[int, int], Decimal] = {}
    for _, row in tax_rows.iterrows():
        gn = _safe_int(row.get("Grant Number"))
        vp = _safe_int(row.get("Vest Period"))
        if gn is None or vp is None:
            continue
        # Taxable gain is the same across all tax types for a vest
        tg = _safe_decimal(row.get("Taxable Gain"))
        wa = _safe_decimal(row.get("Withholding Amount"))
        if tg is not None and (gn, vp) not in vest_fmv_from_tax:
            vest_fmv_from_tax[(gn, vp)] = tg
        if wa is not None:
            key = (gn, vp)
            vest_tax_totals[key] = vest_tax_totals.get(key, Decimal("0")) + wa

    # Get the symbol and latest share price from grant rows
    symbol = str(grant_rows.iloc[0]["Symbol"]) if len(grant_rows) > 0 else "MSFT"

    grants_created = 0
    vests_created = 0

    for _, g in grant_rows.iterrows():
        grant_num = str(int(g["Grant Number"]))
        grant_date = _parse_date(g["Grant Date"])
        total = _safe_int(g["Granted Qty."])
        vested = _safe_int(g["Vested Qty."])
        unvested = _safe_int(g["Unvested Qty."])
        sellable = _safe_int(g["Sellable Qty."])
        mkt_val = _safe_decimal(g["Est. Market Value"])

        # Compute share_price from market value / total shares
        share_price = None
        if mkt_val and total and total > 0:
            share_price = (mkt_val / Decimal(str(total))).quantize(Decimal("0.01"))

        # Upsert grant
        existing = db.get(RSUGrant, grant_num)
        if existing:
            existing.company = "MSFT"
            existing.symbol = symbol
            existing.grant_date = grant_date
            existing.total_shares = total
            existing.vested_shares = vested
            existing.unvested_shares = unvested
            existing.sellable_shares = sellable
            existing.share_price = share_price
        else:
            db.add(RSUGrant(
                id=grant_num,
                company="MSFT",
                symbol=symbol,
                grant_date=grant_date,
                total_shares=total,
                vested_shares=vested,
                unvested_shares=unvested,
                sellable_shares=sellable,
                share_price=share_price,
            ))
            grants_created += 1

        # Build vest events for this grant
        gvests = vest_rows[vest_rows["Grant Number"] == g["Grant Number"]]
        for _, v in gvests.iterrows():
            vd = _parse_date(v["Vest Date"])
            vp = _safe_int(v["Vest Period"])
            shares_vested = _safe_int(v["Vested Qty..1"]) or 0
            shares_released = _safe_int(v["Released Qty"]) or 0
            shares_withheld = _safe_int(v["Shares Traded for taxes"]) or 0
            taxes_paid = _safe_decimal(v["Total Taxes Paid"])

            if vd is None or vp is None:
                continue

            # Determine if this vest has actually happened
            is_actual = shares_vested > 0

            # Cost basis: prefer sellable sheet, fall back to taxable gain / shares
            gn_int = int(g["Grant Number"])
            fmv = cost_basis_map.get((gn_int, vp))
            if fmv is None and is_actual and shares_vested > 0:
                taxable_gain = vest_fmv_from_tax.get((gn_int, vp))
                if taxable_gain is not None:
                    fmv = (taxable_gain / Decimal(str(shares_vested))).quantize(Decimal("0.01"))

            # For future vests, estimate shares per period
            if not is_actual and total and len(gvests) > 0:
                num_periods = len(gvests)
                shares_per = total // num_periods
                extra = 1 if (vp - 1) < (total % num_periods) else 0
                shares_vested = shares_per + extra

            # Tax total from withholding rows if not in vest schedule
            if taxes_paid is None or float(taxes_paid) == 0:
                taxes_paid = vest_tax_totals.get((gn_int, vp))

            # Check for existing vest event
            from sqlalchemy import select, and_
            existing_ve = db.execute(
                select(VestEvent).where(
                    and_(VestEvent.grant_id == grant_num, VestEvent.vest_period == vp)
                )
            ).scalar_one_or_none()

            if existing_ve:
                existing_ve.vest_date = vd
                existing_ve.shares = shares_vested
                existing_ve.fmv_at_vest = fmv
                existing_ve.shares_withheld = shares_withheld if is_actual else None
                existing_ve.shares_released = shares_released if is_actual else None
                existing_ve.total_taxes_paid = taxes_paid if is_actual else None
                existing_ve.is_actual = is_actual
                existing_ve.vest_price = fmv  # keep legacy field in sync
            else:
                db.add(VestEvent(
                    grant_id=grant_num,
                    vest_date=vd,
                    vest_period=vp,
                    shares=shares_vested,
                    fmv_at_vest=fmv,
                    shares_withheld=shares_withheld if is_actual else None,
                    shares_released=shares_released if is_actual else None,
                    total_taxes_paid=taxes_paid if is_actual else None,
                    is_actual=is_actual,
                    vest_price=fmv,
                ))
                vests_created += 1

    # Store current stock price
    # Use the market value and sellable shares to estimate current price
    total_mkt = sum(float(g["Est. Market Value"]) for _, g in grant_rows.iterrows() if pd.notna(g["Est. Market Value"]))
    total_sellable = sum(int(g["Sellable Qty."]) for _, g in grant_rows.iterrows() if pd.notna(g["Sellable Qty."]) and int(g["Sellable Qty."]) > 0)
    if total_sellable > 0:
        current_price = Decimal(str(total_mkt / total_sellable)).quantize(Decimal("0.01"))
    else:
        # Fall back: use total shares
        total_shares_all = sum(int(g["Granted Qty."]) for _, g in grant_rows.iterrows())
        current_price = Decimal(str(total_mkt / total_shares_all)).quantize(Decimal("0.01")) if total_shares_all > 0 else None

    if current_price:
        from sqlalchemy import select
        existing_sp = db.execute(
            select(StockPrice).where(
                StockPrice.symbol == symbol,
                StockPrice.price_date == date.today(),
            )
        ).scalar_one_or_none()
        if existing_sp:
            existing_sp.close_price = current_price
        else:
            db.add(StockPrice(
                symbol=symbol,
                price_date=date.today(),
                close_price=current_price,
                source="etrade_export",
            ))

    db.commit()

    return {
        "grants_created": grants_created,
        "vests_created": vests_created,
        "symbol": symbol,
        "current_price": float(current_price) if current_price else None,
    }
