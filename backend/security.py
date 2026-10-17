"""Security middleware — API auth, rate limiting, input sanitization."""

import hmac
import re
import os
import time
import threading
import ipaddress
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

PUBLIC_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}

DEFAULT_TRUSTED_PROXIES = "127.0.0.1,::1"


# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------

_XSS_RE = re.compile(
    r"<script[^>]*>.*?</script>"   # closed script
    r"|<script[^>]*>"               # unclosed script opener
    r"|</script>"                   # stray closer
    r"|<iframe[^>]*>.*?</iframe>"   # closed iframe
    r"|<iframe[^>]*>",              # unclosed iframe
    re.I | re.S,
)
_SQLI_RE = re.compile(r"\b(union\s+select|drop\s+table|delete\s+from|insert\s+into|truncate\s+table)\b", re.I)
_PATH_RE = re.compile(r"\.\.[\\/]|\x00")

MAX_MESSAGE_LEN = 8000
MAX_FIELD_LEN = 500


def sanitize_text(value: str, max_len: int = MAX_MESSAGE_LEN) -> str:
    """Strip XSS, SQLi and path-traversal payloads from a string."""
    if not isinstance(value, str):
        return value
    value = _XSS_RE.sub("", value)
    value = _SQLI_RE.sub("", value)
    value = _PATH_RE.sub("", value)
    # Reject null bytes entirely
    value = value.replace("\x00", "")
    if len(value) > max_len:
        value = value[:max_len]
    return value


def sanitize_body(body: dict) -> dict:
    """Recursively sanitize every string in a request body."""
    cleaned: dict = {}
    for key, val in body.items():
        if isinstance(val, str):
            limit = MAX_MESSAGE_LEN if key in ("message", "system_prompt", "content") else MAX_FIELD_LEN
            cleaned[key] = sanitize_text(val, limit)
        elif isinstance(val, dict):
            cleaned[key] = sanitize_body(val)
        elif isinstance(val, list):
            cleaned[key] = [
                sanitize_text(v, MAX_FIELD_LEN) if isinstance(v, str)
                else sanitize_body(v) if isinstance(v, dict)
                else v
                for v in val
            ]
        else:
            cleaned[key] = val
    return cleaned


# ---------------------------------------------------------------------------
# Token-bucket rate limiter
# ---------------------------------------------------------------------------

class TokenBucket:
    __slots__ = ("capacity", "tokens", "refill_rate", "updated", "last_seen")

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.updated = time.monotonic()
        self.last_seen = self.updated

    def consume(self, n: int = 1) -> bool:
        now = time.monotonic()
        elapsed = now - self.updated
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.updated = now
        self.last_seen = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


class RateLimiter:
    """Per-client token-bucket rate limiter (thread-safe, with bucket pruning)."""

    IDLE_TTL = 600.0  # drop buckets idle longer than 10 minutes
    MAX_BUCKETS = 5000

    def __init__(self, capacity: int = 30, refill_rate: float = 0.5):
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self._capacity = capacity
        self._refill_rate = refill_rate

    def _prune(self, now: float) -> None:
        idle = [
            key for key, bucket in self._buckets.items()
            if now - bucket.last_seen > self.IDLE_TTL
        ]
        for key in idle:
            del self._buckets[key]
        excess = len(self._buckets) - self.MAX_BUCKETS
        if excess > 0:
            oldest = sorted(self._buckets.items(), key=lambda kv: kv[1].last_seen)
            for key, _ in oldest[:excess]:
                del self._buckets[key]

    def check(self, client_id: str) -> bool:
        with self._lock:
            self._prune(time.monotonic())
            bucket = self._buckets.get(client_id)
            if bucket is None:
                bucket = TokenBucket(self._capacity, self._refill_rate)
                self._buckets[client_id] = bucket
            return bucket.consume()

    def reset(self):
        with self._lock:
            self._buckets.clear()


def _make_limiter() -> RateLimiter:
    """Build global limiter with env-configurable capacity/refill."""
    try:
        cap = int(os.getenv("RATE_LIMIT_CAPACITY", "30"))
    except ValueError:
        cap = 30
    try:
        refill = float(os.getenv("RATE_LIMIT_REFILL", "0.5"))
    except ValueError:
        refill = 0.5
    return RateLimiter(capacity=cap, refill_rate=refill)


_limiter = _make_limiter()


def get_limiter() -> RateLimiter:
    return _limiter


# ---------------------------------------------------------------------------
# Client IP resolution (proxy-aware)
# ---------------------------------------------------------------------------

_trusted_nets_cache: dict[str, list] = {}


def _trusted_proxy_networks() -> list:
    raw = os.getenv("TRUSTED_PROXIES", DEFAULT_TRUSTED_PROXIES)
    nets = _trusted_nets_cache.get(raw)
    if nets is None:
        nets = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                nets.append(ipaddress.ip_network(part, strict=False))
            except ValueError:
                continue
        _trusted_nets_cache[raw] = nets
    return nets


def _is_trusted_proxy(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in net for net in _trusted_proxy_networks())


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    if not _is_trusted_proxy(peer):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first_hop = forwarded.split(",")[0].strip()
        if first_hop:
            return first_hop
    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip
    return peer


# ---------------------------------------------------------------------------
# API key auth
# ---------------------------------------------------------------------------

def _expected_key() -> str:
    return os.getenv("OMNICHAT_API_KEY", "")


def _key_valid(provided: str) -> bool:
    expected = _expected_key()
    if not expected:
        return True  # auth disabled
    return hmac.compare_digest(provided, expected)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class SecurityMiddleware(BaseHTTPMiddleware):
    """Combines rate limiting, input sanitization and optional API-key auth."""

    def __init__(self, app, rate_limit: bool = True, sanitize: bool = True, auth: bool = True):
        super().__init__(app)
        self._rate_limit = rate_limit
        self._sanitize = sanitize
        self._auth = auth

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # --- rate limit ---
        if self._rate_limit and path not in PUBLIC_PATHS:
            if not _limiter.check(_client_ip(request)):
                return JSONResponse(
                    status_code=429,
                    content={"error": "rate_limited", "detail": "Too many requests. Slow down."},
                )

        # --- auth ---
        if self._auth and _expected_key() and path not in PUBLIC_PATHS:
            provided = request.headers.get("x-api-key", "")
            if not provided:
                auth_header = request.headers.get("authorization", "")
                if auth_header.lower().startswith("bearer "):
                    provided = auth_header[7:]
            if not _key_valid(provided):
                return JSONResponse(
                    status_code=401,
                    content={"error": "unauthorized", "detail": "Missing or invalid API key."},
                )

        # --- sanitize JSON body ---
        if self._sanitize and request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                body = await request.json()
                if isinstance(body, dict):
                    cleaned = sanitize_body(body)
                    # Rebuild the body so downstream sees the sanitized version
                    request._body = _json_bytes(cleaned)  # type: ignore[attr-defined]

        return await call_next(request)


def _json_bytes(obj) -> bytes:
    import json as _json
    return _json.dumps(obj).encode()
