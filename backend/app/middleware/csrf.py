"""Origin check on unsafe methods (CSRF).

The session cookie is SameSite=Lax, but "same site" includes every *.markcheli.com subdomain, the
public demo among them, so a page there could POST to the real app with the owner's cookie. This
middleware refuses a POST/PUT/PATCH/DELETE whose Origin (or, without one, Referer) is a different
origin from this app and is not in FINANCE_CORS_ORIGINS.

Not checked:
- requests with X-API-Key: no cookie is involved, and a browser cannot add that header cross-origin
  without a CORS preflight, which CORSMiddleware answers only for the allowed origins;
- requests with neither Origin nor Referer: browsers always send Origin on a cross-origin POST, so
  only non-browser clients (the email worker, curl, tests) arrive without both.
"""
import logging
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings

logger = logging.getLogger("tallied")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _origin_of(url: str) -> str | None:
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def allowed_origins() -> set[str]:
    origins = {o for o in (_origin_of(u) for u in [settings.base_url, *settings.cors_origins]) if o}
    return origins


class OriginCheckMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope["method"] not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if "x-api-key" in headers:
            await self.app(scope, receive, send)
            return
        source = headers.get("origin") or headers.get("referer")
        if source is None:
            await self.app(scope, receive, send)
            return
        origin = _origin_of(source)  # "null" (sandboxed frames, file://) parses to None and is refused
        host = headers.get("host", "").lower()
        same_host = origin is not None and host and urlsplit(origin).netloc == host
        if same_host or origin in allowed_origins():
            await self.app(scope, receive, send)
            return
        logger.warning("Refused cross-origin %s %s from %s", scope["method"], scope.get("path"), source[:200])
        response = JSONResponse({"detail": "Cross-origin request refused"}, status_code=403)
        await response(scope, receive, send)
