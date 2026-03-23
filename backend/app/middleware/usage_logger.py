"""Middleware that logs API usage metrics for /api/v1/ requests."""
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.database import SessionLocal

logger = logging.getLogger("tallied.usage")


class UsageLoggerMiddleware(BaseHTTPMiddleware):
    """Record method, path, status_code, and latency for every /api/v1/ request.

    User/tenant identity is resolved from the JWT cookie or API key after the
    response is produced (best-effort — if auth fails, we still log with
    whatever context is available).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Only track versioned API requests
        if not request.url.path.startswith("/api/v1/"):
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = int((time.perf_counter() - start) * 1000)

        # Extract identity — best effort, don't blow up if unavailable
        try:
            self._record(request, response, latency_ms)
        except Exception:
            logger.debug("Failed to record usage log", exc_info=True)

        return response

    @staticmethod
    def _record(request: Request, response: Response, latency_ms: int) -> None:
        from app.models.api_usage import ApiUsageLog
        from app.models.api_key import ApiKey
        from app.dependencies import ALGORITHM
        from app.config import settings
        from jose import jwt, JWTError

        user_id: int | None = None
        tenant_id: int | None = None
        api_key_id: int | None = None

        # Try API key header first
        raw_key = request.headers.get("X-API-Key")
        if raw_key:
            key_hash = ApiKey.hash_key(raw_key)
            db = SessionLocal()
            try:
                from sqlalchemy import select
                row = db.execute(
                    select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
                ).scalar_one_or_none()
                if row:
                    api_key_id = row.id
                    user_id = row.user_id
                    tenant_id = row.tenant_id
            finally:
                db.close()
        else:
            # Try JWT cookie
            token = request.cookies.get("tallied_token")
            if token:
                try:
                    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
                    user_id = int(payload["sub"])
                    tenant_id = int(payload["tenant_id"])
                except (JWTError, KeyError, ValueError):
                    pass

        if user_id is None or tenant_id is None:
            return  # Can't log without identity

        # Strip the /api/v1 prefix for cleaner path storage
        path = request.url.path.removeprefix("/api/v1")

        db = SessionLocal()
        try:
            log = ApiUsageLog(
                api_key_id=api_key_id,
                user_id=user_id,
                tenant_id=tenant_id,
                method=request.method,
                path=path,
                status_code=response.status_code,
                latency_ms=latency_ms,
            )
            db.add(log)
            db.commit()
        except Exception:
            logger.debug("Failed to write usage log row", exc_info=True)
            db.rollback()
        finally:
            db.close()
