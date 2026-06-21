from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

# Rate limiter (FISMA SI-10 — brute-force protection)
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])

app = FastAPI(
    title="Candidate Selection Board API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl and int(cl) > 100 * 1024 * 1024:
            return JSONResponse(status_code=413, content={"detail": "Request body too large."})
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Set baseline security response headers at the application layer.

    The reverse proxy also adds these in production; setting them here provides
    defense in depth and keeps the API correct when accessed without the proxy.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection for state-changing requests.

    Exempt paths: /auth/* (pre-session), /health, OPTIONS pre-flight.
    Requires X-CSRF-Token header to match the sb_csrf cookie value.
    """

    EXEMPT_PREFIXES = (
        "/api/v1/auth/",
        "/api/v1/health",
    )
    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

    async def dispatch(self, request: Request, call_next):
        if request.method in self.SAFE_METHODS:
            return await call_next(request)
        path = request.url.path
        for prefix in self.EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        cookie_token = request.cookies.get("sb_csrf")
        header_token = request.headers.get("X-CSRF-Token")
        if not cookie_token or not header_token or cookie_token != header_token:
            # In dev bypass mode, skip CSRF enforcement
            if settings.dev_auth_bypass:
                return await call_next(request)
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid."},
            )
        return await call_next(request)


app.add_middleware(CSRFMiddleware)
app.add_middleware(MaxBodySizeMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-CSRF-Token",
        "X-Requested-With",
    ],
)

app.include_router(api_router, prefix="/api/v1")
