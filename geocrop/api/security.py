"""HTTP security for the API: CSRF defence, tight CORS, and standard response headers.

CSRF. The API has no cookies or sessions (a profile is addressed by its random UUID), so the classic "ride the
victim's login cookie" attack has nothing to ride. A malicious web page can still make the visitor's browser send
cross-site requests: create junk profiles or start expensive simulations and diagnoses. For every state-changing
request (POST, PUT, PATCH, DELETE) we therefore require BOTH:
  1. an allow-listed Origin (or, if a browser omits Origin, an allow-listed Referer); and
  2. the custom header  X-GeoCrop-Client: web.
A custom header cannot be added to a cross-site request without a CORS preflight, and CORS only allows the
GeoCrop web origins, so a hostile page can neither send it nor fall back to a plain HTML form post.
Non-browser clients (curl, scripts) simply send the header; they send no Origin, which is allowed.

Allowed origins come from GEOCROP_ALLOWED_ORIGINS (comma-separated); default: the local dev server.
"""
import os
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CLIENT_HEADER = "x-geocrop-client"
CLIENT_VALUE = "web"


def allowed_origins() -> list[str]:
    raw = os.environ.get("GEOCROP_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


def _origin_of(url: str) -> str | None:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else None


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, origins: list[str]):
        super().__init__(app)
        self.origins = set(origins)

    async def dispatch(self, request, call_next):
        if request.method in UNSAFE:
            origin = request.headers.get("origin")
            if origin is None and request.headers.get("referer"):
                origin = _origin_of(request.headers["referer"])
            if origin is not None and origin.rstrip("/") not in self.origins:
                return JSONResponse({"detail": "cross-site request blocked (origin not allowed)"}, status_code=403)
            if request.headers.get(CLIENT_HEADER) != CLIENT_VALUE:
                return JSONResponse({"detail": f"missing {CLIENT_HEADER} header (CSRF protection)"}, status_code=403)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        r = await call_next(request)
        r.headers.setdefault("X-Content-Type-Options", "nosniff")
        r.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        r.headers.setdefault("X-Frame-Options", "DENY")
        r.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        return r
