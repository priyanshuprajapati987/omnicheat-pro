"""Security tests — sanitization, rate limiting, API auth."""

import time
import pytest
from fastapi.testclient import TestClient

from security import (
    sanitize_text,
    sanitize_body,
    TokenBucket,
    RateLimiter,
    _key_valid,
    _expected_key,
    SecurityMiddleware,
)


# ---------------------------------------------------------------------------
# Input sanitization — unit tests
# ---------------------------------------------------------------------------

class TestSanitizeText:
    def test_strips_script_tag(self):
        assert "<script" not in sanitize_text("<script>alert(1)</script>hi")

    def test_strips_iframe(self):
        assert "<iframe" not in sanitize_text('<iframe src="evil"></iframe>ok')

    def test_strips_union_select(self):
        out = sanitize_text("1 union select password from users")
        assert "union select" not in out.lower()

    def test_strips_drop_table(self):
        assert "drop table" not in sanitize_text("x; drop table users").lower()

    def test_strips_path_traversal(self):
        assert ".." not in sanitize_text("../../etc/passwd")

    def test_strips_null_byte(self):
        assert "\x00" not in sanitize_text("abc\x00def")

    def test_truncates_long_input(self):
        out = sanitize_text("a" * 20000)
        assert len(out) <= 8000

    def test_truncates_short_field(self):
        out = sanitize_text("b" * 2000, max_len=100)
        assert len(out) == 100

    def test_passes_normal_text(self):
        assert sanitize_text("Hello, how are you?") == "Hello, how are you?"

    def test_non_string_passthrough(self):
        assert sanitize_text(123) == 123  # type: ignore[arg-type]

    def test_empty_string(self):
        assert sanitize_text("") == ""

    def test_multiline_code_preserved(self):
        code = "def foo():\n    return 42"
        assert sanitize_text(code) == code


class TestSanitizeBody:
    def test_sanitizes_nested_strings(self):
        body = {"a": {"b": "<script>x</script>"}}
        out = sanitize_body(body)
        assert "<script" not in out["a"]["b"]

    def test_sanitizes_list_items(self):
        out = sanitize_body({"tags": ["<script>1", "ok"]})
        assert "<script" not in out["tags"][0]
        assert out["tags"][1] == "ok"

    def test_truncates_message_field(self):
        out = sanitize_body({"message": "x" * 20000})
        assert len(out["message"]) <= 8000

    def test_truncates_short_field(self):
        out = sanitize_body({"model": "y" * 2000})
        assert len(out["model"]) <= 500

    def test_preserves_non_strings(self):
        out = sanitize_body({"n": 42, "f": 1.5, "b": True, "nul": None})
        assert out == {"n": 42, "f": 1.5, "b": True, "nul": None}

    def test_dict_in_list(self):
        out = sanitize_body({"items": [{"cmd": "rm -rf <script>"}]})
        assert "<script" not in out["items"][0]["cmd"]


# ---------------------------------------------------------------------------
# Rate limiter — unit tests
# ---------------------------------------------------------------------------

class TestTokenBucket:
    def test_consume_within_capacity(self):
        b = TokenBucket(capacity=5, refill_rate=1.0)
        assert all(b.consume() for _ in range(5))

    def test_exhaustion(self):
        b = TokenBucket(capacity=2, refill_rate=0.001)
        b.consume(); b.consume()
        assert b.consume() is False

    def test_refill(self):
        b = TokenBucket(capacity=2, refill_rate=1000.0)  # fast refill
        b.consume(); b.consume()
        time.sleep(0.05)
        assert b.consume() is True

    def test_never_exceeds_capacity(self):
        b = TokenBucket(capacity=3, refill_rate=10000.0)
        time.sleep(0.1)
        assert b.tokens <= 3


class TestRateLimiter:
    def test_allows_within_capacity(self):
        rl = RateLimiter(capacity=5, refill_rate=0.001)
        assert all(rl.check("client-a") for _ in range(5))

    def test_blocks_after_exhaustion(self):
        rl = RateLimiter(capacity=3, refill_rate=0.001)
        for _ in range(3):
            rl.check("client-b")
        assert rl.check("client-b") is False

    def test_isolation_between_clients(self):
        rl = RateLimiter(capacity=2, refill_rate=0.001)
        rl.check("x"); rl.check("x")
        assert rl.check("x") is False
        assert rl.check("y") is True  # independent bucket

    def test_reset(self):
        rl = RateLimiter(capacity=1, refill_rate=0.001)
        rl.check("z"); rl.check("z")
        rl.reset()
        assert rl.check("z") is True


# ---------------------------------------------------------------------------
# API key validation
# ---------------------------------------------------------------------------

class TestApiKey:
    def test_disabled_when_unset(self, monkeypatch):
        monkeypatch.delenv("OMNICHAT_API_KEY", raising=False)
        assert _expected_key() == ""
        assert _key_valid("") is True  # auth off → everything allowed

    def test_valid_key(self, monkeypatch):
        monkeypatch.setenv("OMNICHAT_API_KEY", "secret123")
        assert _key_valid("secret123") is True

    def test_invalid_key(self, monkeypatch):
        monkeypatch.setenv("OMNICHAT_API_KEY", "secret123")
        assert _key_valid("wrong") is False

    def test_empty_key_when_auth_on(self, monkeypatch):
        monkeypatch.setenv("OMNICHAT_API_KEY", "secret123")
        assert _key_valid("") is False


# ---------------------------------------------------------------------------
# Middleware — integration tests
# ---------------------------------------------------------------------------

class TestSecurityMiddleware:
    @pytest.fixture
    def app(self):
        from main import app as _app
        return _app

    def test_public_paths_not_rate_limited(self, app):
        # /health is public — should never 429 from auth/rate path
        with TestClient(app) as c:
            for _ in range(5):
                assert c.get("/health").status_code == 200

    def test_api_auth_401_when_key_required(self, monkeypatch):
        monkeypatch.setenv("OMNICHAT_API_KEY", "test-key-xyz")
        from main import app as _app
        with TestClient(_app) as c:
            r = c.get("/api/agents/")  # no key
            assert r.status_code == 401
            r2 = c.get("/api/agents/", headers={"x-api-key": "test-key-xyz"})
            assert r2.status_code == 200

    def test_auth_via_bearer_header(self, monkeypatch):
        monkeypatch.setenv("OMNICHAT_API_KEY", "bk")
        from main import app as _app
        with TestClient(_app) as c:
            r = c.get("/api/agents/", headers={"authorization": "Bearer bk"})
            assert r.status_code == 200

    def test_auth_off_by_default(self, monkeypatch):
        monkeypatch.delenv("OMNICHAT_API_KEY", raising=False)
        from main import app as _app
        with TestClient(_app) as c:
            assert c.get("/api/agents/").status_code == 200

    def test_rate_limit_429_after_burst(self, monkeypatch):
        monkeypatch.delenv("OMNICHAT_API_KEY", raising=False)
        from security import get_limiter
        get_limiter().reset()
        from main import app as _app
        with TestClient(_app) as c:
            codes = [c.get("/api/agents/").status_code for _ in range(35)]
            # First ~30 should be 200, later ones 429
            assert 429 in codes
            assert codes[0] == 200
        get_limiter().reset()

    def test_sanitized_body_strips_xss(self, monkeypatch):
        monkeypatch.delenv("OMNICHAT_API_KEY", raising=False)
        from main import app as _app
        from unittest.mock import AsyncMock, patch as _patch
        from agents.executor import AgentResult
        with TestClient(_app) as c:
            with _patch("routes.chat.get_executor") as mock_ge:
                mock_ge.return_value = AsyncMock(
                    execute=AsyncMock(return_value=AgentResult(success=True, output="ok"))
                )
                r = c.post("/api/chat/send", json={"message": "<script>alert(1)</script>hi"})
                assert r.status_code == 200
                # Sanitizer should have stripped the script tag before executor saw it
                call_kwargs = mock_ge.return_value.execute.call_args
                assert "<script" not in call_kwargs.kwargs.get("message", "")

    def test_middleware_disabled_flags(self):
        # Constructible with all features off
        from main import app as _app
        m = SecurityMiddleware(_app, rate_limit=False, sanitize=False, auth=False)
        assert m._rate_limit is False
        assert m._sanitize is False
        assert m._auth is False
