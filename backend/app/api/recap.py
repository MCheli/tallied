from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_tenant_db
from app.services import recap_email
from app.services.weekly_recap import month_pace, weekly_recap

router = APIRouter(prefix="/recap", tags=["recap"])


@router.get("/weekly")
def get_weekly_recap(
    week_start: date | None = Query(None, description="Any day of the week wanted; default the last completed Sunday–Saturday week"),
    db: Session = Depends(get_tenant_db),
):
    """One week's recap: net worth change, spending against the prior four-week average, top categories,
    largest purchases, income, the bills due the week after and RSU vests in the next 30 days."""
    return weekly_recap(db, date.today(), week_start)


@router.get("/weekly/email")
def get_weekly_recap_email(
    week_start: date | None = Query(None, description="Any day of the week wanted; default the last completed week"),
    db: Session = Depends(get_tenant_db),
):
    """The recap as an email (subject, html, text). The weekly-recap Cloudflare worker fetches this on
    Monday mornings with a read-only API key and sends it; this route sends nothing."""
    return recap_email.render(weekly_recap(db, date.today(), week_start), settings.base_url)


@router.get("/month-pace")
def get_month_pace(
    month: date | None = Query(None, description="Any day of the month wanted; default this month"),
    db: Session = Depends(get_tenant_db),
):
    """Cumulative spending by day of month, this month against last month."""
    return month_pace(db, date.today(), month)
