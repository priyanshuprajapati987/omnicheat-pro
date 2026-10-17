"""Regression tests for audit fixes: history order, provider fallback, gemini
history, async tools, embed dims, proxy-aware rate limiting, tokens_used."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

with patch.dict("os.environ", {"OLLAMA_URL": ""}, clear=False):
    from main import app
    from llm.router import LLMRouter, LLMResponse
    from agents.executor import AgentExecutor
    from memory.vector_store import ConversationMemory, MemoryEntry, get_embedder
    from security import RateLimiter, _client_ip


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from security import get_limiter
    get_limiter().reset()
    yield
    get_limiter().reset()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _make_memory() -> ConversationMemory:
    with patch.object(ConversationMemory, "_ensure_collection", lambda self: None):
        mem = ConversationMemory()
    mem.client = None
    mem._connected = False
    return mem


class _FakePoint:
    def __init__(self, id, payload):
        self.id = id
        self.payload = payload


class _FakeQdrantClient:
    def __init__(self, points=None):
        self._points = points or []

    def scroll(self, **kwargs):
        return (self._points, None)

    def search(self, **kwargs):
        return []

    def upsert(self, **kwargs):
        return None

    def delete(self, **kwargs):
        return None


# ---------------------------------------------------------------------------
# Item 3 — get_history always chronological (both branches)
# ---------------------------------------------------------------------------

class TestHistoryChronological:
    async def test_in_memory_branch_oldest_first(self):
        mem = _make_memory()
        for i in range(5):
            await mem.add("hist", "user", f"msg-{i}", embedding=[0.0] * 384)
        hist = await mem.get_history("hist")
        assert [e.content for e in hist] == [f"msg-{i}" for i in range(5)]

    async def test_qdrant_branch_sorted_by_created_at(self):
        mem = _make_memory()
        mem._connected = True
        mem.client = _FakeQdrantClient([
            _FakePoint("3", {"session_id": "q", "role": "assistant", "content": "third",
                             "created_at": "2026-01-03T00:00:00"}),
            _FakePoint("1", {"session_id": "q", "role": "user", "content": "first",
                             "created_at": "2026-01-01T00:00:00"}),
            _FakePoint("2", {"session_id": "q", "role": "user", "content": "second",
                             "created_at": "2026-01-02T00:00:00"}),
        ])
        hist = await mem.get_history("q")
        assert [e.content for e in hist] == ["first", "second", "third"]

    async def test_qdrant_branch_limit_keeps_most_recent_chronological(self):
        mem = _make_memory()
        mem._connected = True
        mem.client = _FakeQdrantClient([
            _FakePoint("1", {"session_id": "q2", "role": "user", "content": "first",
                             "created_at": "2026-01-01T00:00:00"}),
            _FakePoint("2", {"session_id": "q2", "role": "assistant", "content": "second",
                             "created_at": "2026-01-02T00:00:00"}),
            _FakePoint("3", {"session_id": "q2", "role": "user", "content": "third",
                             "created_at": "2026-01-03T00:00:00"}),
        ])
        hist = await mem.get_history("q2", limit=2)
        assert [e.content for e in hist] == ["second", "third"]

    async def test_executor_history_iterates_chronologically(self):
        ex = AgentExecutor.__new__(AgentExecutor)
        ex.memory = AsyncMock()
        ex.memory.get_history = AsyncMock(return_value=[
            MemoryEntry(id="1", session_id="s", role="user", content="first"),
            MemoryEntry(id="2", session_id="s", role="assistant", content="second"),
        ])
        hist = await ex._get_history("s")
        assert [h["content"] for h in hist] == ["first", "second"]

    def test_stream_route_history_chronological(self, client):
        captured = {}

        async def fake_stream(model, messages, temperature=0.7):
            captured["messages"] = messages
            yield "ok"

        entries = [
            MemoryEntry(id="1", session_id="s-order", role="user", content="older-user"),
            MemoryEntry(id="2", session_id="s-order", role="assistant", content="older-assistant"),
        ]
        with patch("routes.chat.get_router") as mock_gr, \
             patch("routes.chat.get_memory") as mock_gm:
            mock_gr.return_value = MagicMock(stream=fake_stream)
            mock_mem = AsyncMock()
            mock_mem.get_history = AsyncMock(return_value=entries)
            mock_mem.add = AsyncMock()
            mock_gm.return_value = mock_mem
            r = client.post(
                "/api/chat/stream",
                json={"message": "current-question", "model": "qwen3:1.7b", "session_id": "s-order"},
            )
        assert r.status_code == 200
        msgs = captured["messages"]
        assert msgs[0]["role"] == "system"
        assert msgs[1]["content"] == "older-user"
        assert msgs[2]["content"] == "older-assistant"
        assert msgs[3]["content"] == "current-question"


# ---------------------------------------------------------------------------
# Item 7 — embed dims + empty-Qdrant fallback
# ---------------------------------------------------------------------------

class TestEmbedderAndFallback:
    async def test_embed_produces_384_dims(self):
        emb = await get_embedder().embed("hello world")
        assert len(emb) == 384

    async def test_embed_deterministic(self):
        embedder = get_embedder()
        a = await embedder.embed("same text")
        b = await embedder.embed("same text")
        assert a == b

    async def test_qdrant_empty_history_falls_back_to_memory(self):
        mem = _make_memory()
        mem._connected = True
        mem.client = _FakeQdrantClient(points=[])
        await mem.add("fb", "user", "kept-in-memory", embedding=[0.0] * 384)
        hist = await mem.get_history("fb")
        assert [e.content for e in hist] == ["kept-in-memory"]

    async def test_qdrant_empty_recall_falls_back_to_memory(self):
        mem = _make_memory()
        mem._connected = True
        mem.client = _FakeQdrantClient(points=[])
        await mem.add("fb2", "user", "recalled", embedding=[0.0] * 384)
        entries = await mem.recall("fb2", [0.0] * 384)
        assert any(e.content == "recalled" for e in entries)


# ---------------------------------------------------------------------------
# Items 4 + 13 — /send 502 shape, router fallback, tokens_used
# ---------------------------------------------------------------------------

class TestSendErrorHandling:
    def test_send_502_body_shape_when_executor_raises(self, client):
        with patch("routes.chat.get_executor") as mock_ge:
            mock_ge.return_value = AsyncMock(
                execute=AsyncMock(side_effect=ValueError("Provider not available: openai"))
            )
            r = client.post("/api/chat/send", json={"message": "hi", "model": "gpt-3.5-turbo"})
        assert r.status_code == 502
        data = r.json()
        assert set(data.keys()) == {"error", "provider", "hint"}
        assert "Provider not available" in data["error"]
        assert data["provider"] == "openai"
        assert "Ollama" in data["hint"]

    def test_send_502_when_provider_http_error(self, client):
        with patch("routes.chat.get_executor") as mock_ge:
            mock_ge.return_value = AsyncMock(
                execute=AsyncMock(side_effect=RuntimeError("connection refused"))
            )
            r = client.post("/api/chat/send", json={"message": "hi", "model": "llama3.2"})
        assert r.status_code == 502
        data = r.json()
        assert data["error"] == "connection refused"
        assert data["provider"] == "ollama"

    def test_send_returns_tokens_used(self, client):
        from agents.executor import AgentResult
        result = AgentResult(success=True, output="ok", tokens_used=42)
        with patch("routes.chat.get_executor") as mock_ge:
            mock_ge.return_value = AsyncMock(execute=AsyncMock(return_value=result))
            r = client.post("/api/chat/send", json={"message": "hi", "model": "qwen3:1.7b"})
        assert r.status_code == 200
        assert r.json()["tokens_used"] == 42


class TestRouterFallback:
    def test_generate_falls_back_to_first_configured_provider(self):
        with patch.dict("os.environ", {
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OLLAMA_URL": "http://127.0.0.1:11434",
        }):
            router = LLMRouter()
        fake = MagicMock()
        fake.generate = AsyncMock(return_value=LLMResponse(
            content="fallback-ok", model="llama2", provider="ollama"
        ))
        router.providers = {"ollama": fake}
        resp = asyncio.run(router.generate(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "hi"}],
        ))
        assert resp.content == "fallback-ok"
        fake.generate.assert_awaited_once()

    def test_stream_falls_back_to_first_configured_provider(self):
        with patch.dict("os.environ", {
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OLLAMA_URL": "http://127.0.0.1:11434",
        }):
            router = LLMRouter()

        async def fake_stream(model, messages, temperature=0.7):
            yield "tok"

        fake = MagicMock()
        fake.stream = fake_stream
        router.providers = {"ollama": fake}

        async def consume():
            return [t async for t in router.stream(model="gpt-3.5-turbo", messages=[])]

        assert asyncio.run(consume()) == ["tok"]

    def test_exact_provider_still_preferred(self):
        router = LLMRouter()
        preferred = MagicMock()
        preferred.generate = AsyncMock(return_value=LLMResponse(
            content="openai-answer", model="gpt-4", provider="openai"
        ))
        other = MagicMock()
        other.generate = AsyncMock(return_value=LLMResponse(
            content="other-answer", model="x", provider="ollama"
        ))
        router.providers = {"ollama": other, "openai": preferred}
        resp = asyncio.run(router.generate(model="gpt-4", messages=[]))
        assert resp.content == "openai-answer"
        other.generate.assert_not_awaited()

    def test_no_providers_still_raises(self):
        router = LLMRouter()
        router.providers = {}
        with pytest.raises(ValueError):
            asyncio.run(router.generate(model="gpt-4", messages=[]))


# ---------------------------------------------------------------------------
# Item 5 — Gemini passes full chat history
# ---------------------------------------------------------------------------

class TestGeminiFullHistory:
    def test_passes_full_history_not_last_message(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        import llm.providers.google_provider as gp

        captured = {}

        class FakeResponse:
            text = "gemini-reply"
            usage_metadata = None

        class FakeModel:
            def __init__(self, model_name=None, system_instruction=None):
                captured["system_instruction"] = system_instruction

            async def generate_content_async(self, contents, generation_config=None):
                captured["contents"] = contents
                captured["generation_config"] = generation_config
                return FakeResponse()

        with patch.object(gp.genai, "GenerativeModel", FakeModel):
            provider = gp.GoogleProvider()
            resp = asyncio.run(provider.generate("gemini-pro", [
                {"role": "system", "content": "be brief"},
                {"role": "user", "content": "first question"},
                {"role": "assistant", "content": "first answer"},
                {"role": "user", "content": "follow up"},
            ]))

        assert captured["contents"] == [
            {"role": "user", "parts": ["first question"]},
            {"role": "model", "parts": ["first answer"]},
            {"role": "user", "parts": ["follow up"]},
        ]
        assert captured["system_instruction"] == "be brief"
        assert resp.content == "gemini-reply"

    def test_empty_history_passes_empty_string(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        import llm.providers.google_provider as gp

        captured = {}

        class FakeResponse:
            text = "hi"
            usage_metadata = None

        class FakeModel:
            def __init__(self, model_name=None, system_instruction=None):
                pass

            async def generate_content_async(self, contents, generation_config=None):
                captured["contents"] = contents
                return FakeResponse()

        with patch.object(gp.genai, "GenerativeModel", FakeModel):
            provider = gp.GoogleProvider()
            asyncio.run(provider.generate("gemini-pro", [
                {"role": "system", "content": "sys only"},
            ]))
        assert captured["contents"] == ""


# ---------------------------------------------------------------------------
# Item 6 — WebSearchTool off event loop
# ---------------------------------------------------------------------------

class TestWebSearchTool:
    async def test_search_still_works_via_to_thread(self):
        from tools.registry import WebSearchTool

        class FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def text(self, query, max_results=5):
                return [{"title": "Result", "href": "http://example.com", "body": "body text"}]

        with patch("tools.registry.DDGS", FakeDDGS):
            res = await WebSearchTool().search("hello")
        assert res.success is True
        assert "Result" in res.output
        assert "http://example.com" in res.output

    async def test_search_error_is_captured(self):
        from tools.registry import WebSearchTool

        class FakeDDGS:
            def __enter__(self):
                raise RuntimeError("ddgs down")

            def __exit__(self, *args):
                return False

        with patch("tools.registry.DDGS", FakeDDGS):
            res = await WebSearchTool().search("hello")
        assert res.success is False
        assert "ddgs down" in res.error


# ---------------------------------------------------------------------------
# Item 8 — proxy-aware client IP + bucket pruning
# ---------------------------------------------------------------------------

def _make_request(peer="testclient", headers=None):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/agents/",
        "raw_path": b"/api/agents/",
        "query_string": b"",
        "headers": raw,
        "client": (peer, 1234),
        "server": ("testserver", 80),
    }
    return Request(scope)


class TestClientIPResolution:
    def test_xff_honored_when_peer_trusted(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1,::1")
        req = _make_request(
            peer="127.0.0.1",
            headers={"X-Forwarded-For": "203.0.113.9, 172.16.0.1"},
        )
        assert _client_ip(req) == "203.0.113.9"

    def test_xff_ignored_when_peer_untrusted(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1,::1")
        req = _make_request(
            peer="10.9.8.7",
            headers={"X-Forwarded-For": "203.0.113.9"},
        )
        assert _client_ip(req) == "10.9.8.7"

    def test_x_real_ip_used_when_no_xff(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1,::1")
        req = _make_request(peer="::1", headers={"X-Real-IP": "198.51.100.7"})
        assert _client_ip(req) == "198.51.100.7"

    def test_trusted_peer_without_headers_returns_peer(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1,::1")
        req = _make_request(peer="127.0.0.1")
        assert _client_ip(req) == "127.0.0.1"

    def test_custom_cidr_trusted_proxies(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.0/8")
        req = _make_request(peer="10.1.2.3", headers={"X-Forwarded-For": "198.18.0.1"})
        assert _client_ip(req) == "198.18.0.1"
        # loopback no longer trusted under custom list
        req2 = _make_request(peer="127.0.0.1", headers={"X-Forwarded-For": "198.18.0.1"})
        assert _client_ip(req2) == "127.0.0.1"

    def test_malformed_xff_falls_back(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1,::1")
        req = _make_request(peer="127.0.0.1", headers={"X-Forwarded-For": "  "})
        assert _client_ip(req) == "127.0.0.1"

    def test_non_ip_peer_is_untrusted(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1,::1")
        req = _make_request(peer="testclient", headers={"X-Forwarded-For": "203.0.113.9"})
        assert _client_ip(req) == "testclient"

    def test_middleware_uses_forwarded_ip_from_trusted_peer(self, monkeypatch):
        monkeypatch.delenv("OMNICHAT_API_KEY", raising=False)
        monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1,::1")
        seen = []
        mock_limiter = MagicMock()
        mock_limiter.check = lambda cid: seen.append(cid) or True
        from main import app as _app
        with patch("security._limiter", mock_limiter):
            with TestClient(_app, client=("127.0.0.1", 50000)) as c:
                c.get("/api/agents/", headers={"X-Forwarded-For": "203.0.113.9"})
        assert seen and seen[0] == "203.0.113.9"


class TestRateLimiterPruning:
    def test_idle_buckets_pruned_on_check(self):
        rl = RateLimiter(capacity=5, refill_rate=0.001)
        rl.check("old-client")
        with rl._lock:
            rl._buckets["old-client"].last_seen = time.monotonic() - 700
        rl.check("fresh-client")
        assert "old-client" not in rl._buckets
        assert "fresh-client" in rl._buckets

    def test_active_buckets_kept(self):
        rl = RateLimiter(capacity=5, refill_rate=0.001)
        rl.check("active")
        rl.check("other")
        assert "active" in rl._buckets
        assert "other" in rl._buckets

    def test_cap_evicts_oldest(self):
        rl = RateLimiter(capacity=5, refill_rate=0.001)
        rl.MAX_BUCKETS = 3
        for i in range(5):
            rl.check(f"c{i}")
        # prune runs on each check: oldest buckets are evicted to respect the cap
        assert len(rl._buckets) <= 4
        assert "c0" not in rl._buckets
        assert "c4" in rl._buckets

    def test_token_bucket_exposes_last_seen(self):
        rl = RateLimiter(capacity=5, refill_rate=0.001)
        rl.check("client-x")
        with rl._lock:
            assert rl._buckets["client-x"].last_seen > 0
