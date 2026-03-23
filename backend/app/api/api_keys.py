"""API key management and usage tracking endpoints."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import TenantContext, get_tenant_context
from app.models.api_key import ApiKey
from app.models.api_usage import ApiUsageLog

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class CreateApiKeyRequest(BaseModel):
    name: str
    permissions: str = "read"  # read, write, admin


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    permissions: str
    is_active: bool
    last_used: str | None = None
    created_at: str | None = None


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Returned only on creation — includes the full key (shown once)."""
    key: str


@router.get("/", response_model=list[ApiKeyResponse])
def list_api_keys(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    """List all API keys for the current user's active tenant."""
    keys = db.execute(
        select(ApiKey).where(
            ApiKey.user_id == ctx.user_id,
            ApiKey.tenant_id == ctx.tenant_id,
        ).order_by(ApiKey.created_at.desc())
    ).scalars().all()

    return [
        ApiKeyResponse(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            permissions=k.permissions,
            is_active=k.is_active,
            last_used=k.last_used.isoformat() if k.last_used else None,
            created_at=k.created_at.isoformat() if k.created_at else None,
        )
        for k in keys
    ]


@router.post("/", response_model=ApiKeyCreatedResponse, status_code=201)
def create_api_key(
    body: CreateApiKeyRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Create a new API key. The full key is returned only once."""
    if body.permissions not in ("read", "write", "admin"):
        raise HTTPException(status_code=400, detail="Permissions must be read, write, or admin")

    raw_key = ApiKey.generate_key()
    key_hash = ApiKey.hash_key(raw_key)

    api_key = ApiKey(
        user_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        name=body.name,
        key_prefix=raw_key[:12],
        key_hash=key_hash,
        permissions=body.permissions,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return ApiKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        permissions=api_key.permissions,
        is_active=True,
        created_at=api_key.created_at.isoformat() if api_key.created_at else None,
        key=raw_key,
    )


@router.delete("/{key_id}")
def revoke_api_key(
    key_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Revoke (deactivate) an API key."""
    api_key = db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.user_id == ctx.user_id,
        )
    ).scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.is_active = False
    db.commit()
    return {"message": "API key revoked"}


# ── Usage tracking endpoints ─────────────────────────────────────────────────

class EndpointUsage(BaseModel):
    path: str
    method: str
    count: int


class KeyUsageResponse(BaseModel):
    key_id: int
    key_name: str
    total_requests: int
    requests_last_24h: int
    requests_last_hour: int
    avg_latency_ms: float
    top_endpoints: list[EndpointUsage]


class UsageSummaryResponse(BaseModel):
    total_requests_today: int
    requests_last_hour: int
    total_requests_all_time: int
    avg_latency_ms: float
    top_endpoints: list[EndpointUsage]
    per_key: list[KeyUsageResponse]


@router.get("/{key_id}/usage", response_model=KeyUsageResponse)
def get_key_usage(
    key_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Usage stats for a specific API key."""
    api_key = db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.user_id == ctx.user_id,
            ApiKey.tenant_id == ctx.tenant_id,
        )
    ).scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(hours=24)

    base = select(ApiUsageLog).where(ApiUsageLog.api_key_id == key_id)

    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar() or 0

    last_24h = db.execute(
        select(func.count()).where(
            ApiUsageLog.api_key_id == key_id,
            ApiUsageLog.timestamp >= one_day_ago,
        )
    ).scalar() or 0

    last_hour = db.execute(
        select(func.count()).where(
            ApiUsageLog.api_key_id == key_id,
            ApiUsageLog.timestamp >= one_hour_ago,
        )
    ).scalar() or 0

    avg_latency = db.execute(
        select(func.avg(ApiUsageLog.latency_ms)).where(
            ApiUsageLog.api_key_id == key_id,
        )
    ).scalar() or 0.0

    top_eps = db.execute(
        select(
            ApiUsageLog.path,
            ApiUsageLog.method,
            func.count().label("cnt"),
        ).where(
            ApiUsageLog.api_key_id == key_id,
        ).group_by(ApiUsageLog.path, ApiUsageLog.method)
        .order_by(func.count().desc())
        .limit(10)
    ).all()

    return KeyUsageResponse(
        key_id=api_key.id,
        key_name=api_key.name,
        total_requests=total,
        requests_last_24h=last_24h,
        requests_last_hour=last_hour,
        avg_latency_ms=round(float(avg_latency), 1),
        top_endpoints=[EndpointUsage(path=r[0], method=r[1], count=r[2]) for r in top_eps],
    )


@router.get("/usage/summary", response_model=UsageSummaryResponse)
def get_usage_summary(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Aggregate usage across all keys and cookie auth for the current tenant."""
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    tenant_filter = ApiUsageLog.tenant_id == ctx.tenant_id

    total_all = db.execute(
        select(func.count()).where(tenant_filter)
    ).scalar() or 0

    total_today = db.execute(
        select(func.count()).where(tenant_filter, ApiUsageLog.timestamp >= today_start)
    ).scalar() or 0

    last_hour = db.execute(
        select(func.count()).where(tenant_filter, ApiUsageLog.timestamp >= one_hour_ago)
    ).scalar() or 0

    avg_latency = db.execute(
        select(func.avg(ApiUsageLog.latency_ms)).where(tenant_filter)
    ).scalar() or 0.0

    top_eps = db.execute(
        select(
            ApiUsageLog.path,
            ApiUsageLog.method,
            func.count().label("cnt"),
        ).where(tenant_filter)
        .group_by(ApiUsageLog.path, ApiUsageLog.method)
        .order_by(func.count().desc())
        .limit(10)
    ).all()

    # Per-key breakdown
    keys = db.execute(
        select(ApiKey).where(
            ApiKey.user_id == ctx.user_id,
            ApiKey.tenant_id == ctx.tenant_id,
        )
    ).scalars().all()

    per_key: list[KeyUsageResponse] = []
    for k in keys:
        k_total = db.execute(
            select(func.count()).where(ApiUsageLog.api_key_id == k.id)
        ).scalar() or 0
        k_24h = db.execute(
            select(func.count()).where(
                ApiUsageLog.api_key_id == k.id,
                ApiUsageLog.timestamp >= now - timedelta(hours=24),
            )
        ).scalar() or 0
        k_hour = db.execute(
            select(func.count()).where(
                ApiUsageLog.api_key_id == k.id,
                ApiUsageLog.timestamp >= one_hour_ago,
            )
        ).scalar() or 0
        k_avg = db.execute(
            select(func.avg(ApiUsageLog.latency_ms)).where(ApiUsageLog.api_key_id == k.id)
        ).scalar() or 0.0

        per_key.append(KeyUsageResponse(
            key_id=k.id,
            key_name=k.name,
            total_requests=k_total,
            requests_last_24h=k_24h,
            requests_last_hour=k_hour,
            avg_latency_ms=round(float(k_avg), 1),
            top_endpoints=[],
        ))

    return UsageSummaryResponse(
        total_requests_today=total_today,
        requests_last_hour=last_hour,
        total_requests_all_time=total_all,
        avg_latency_ms=round(float(avg_latency), 1),
        top_endpoints=[EndpointUsage(path=r[0], method=r[1], count=r[2]) for r in top_eps],
        per_key=per_key,
    )
