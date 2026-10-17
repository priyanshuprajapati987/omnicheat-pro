"""Expanded edge-case tests — chat, streaming, agents, memory, executor, router."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

with patch.dict("os.environ", {"OLLAMA_URL": ""}, clear=False):
    from main import app
    from llm.router import LLMRouter
    from agents.executor import AgentResult, get_executor
    from memory.vector_store import get_memory, ConversationMemory


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


# ---------------------------------------------------------------------------
# Chat — edge cases
# ---------------------------------------------------------------------------

class TestChatEdgeCases:
    @pytest.fixture(autouse=True)
    def _mock_executor(self):
        from agents.executor import AgentResult
        result = AgentResult(success=True, output="ok")
        with patch("routes.chat.get_executor") as m:
            m.return_value = AsyncMock(execute=AsyncMock(return_value=result))
            yield m

    def test_send_empty_message(self, client):
        r = client.post("/api/chat/send", json={"message": ""})
        # Should be accepted (empty string) or 422 — both are safe behavior
        assert r.status_code in (200, 422)

    def test_send_very_long_message(self, client):
        r = client.post("/api/chat/send", json={"message": "x" * 50000})
        # Sanitizer truncates to 8000 — executor still runs
        assert r.status_code in (200, 422)

    def test_send_invalid_agent_type(self, client):
        r = client.post("/api/chat/send", json={"message": "hi", "agent_type": "nonexistent"})
        # Executor should handle unknown agent gracefully
        assert r.status_code in (200, 422)

    def test_send_invalid_temperature(self, client):
        r = client.post("/api/chat/send", json={"message": "hi", "temperature": 99})
        assert r.status_code in (200, 422)

    def test_send_negative_temperature(self, client):
        r = client.post("/api/chat/send", json={"message": "hi", "temperature": -5})
        assert r.status_code in (200, 422)

    def test_send_missing_message_field(self, client):
        r = client.post("/api/chat/send", json={"model": "qwen3:1.7b"})
        assert r.status_code == 422

    def test_send_non_json_body(self, client):
        r = client.post(
            "/api/chat/send",
            data="not json",
            headers={"content-type": "text/plain"},
        )
        assert r.status_code in (400, 415, 422)

    def test_send_null_json(self, client):
        r = client.post(
            "/api/chat/send",
            content="null",
            headers={"content-type": "application/json"},
        )
        assert r.status_code in (400, 422)

    def test_send_array_json(self, client):
        r = client.post(
            "/api/chat/send",
            content="[1,2,3]",
            headers={"content-type": "application/json"},
        )
        assert r.status_code in (400, 422)

    def test_session_id_roundtrip(self, client, mock_agent_result=None):
        from agents.executor import AgentResult
        result = AgentResult(success=True, output="ok")
        with patch("routes.chat.get_executor") as mock_ge:
            mock_ge.return_value = AsyncMock(execute=AsyncMock(return_value=result))
            sid = f"sess-{uuid.uuid4().hex[:8]}"
            r = client.post("/api/chat/send", json={"message": "hi", "session_id": sid})
            assert r.status_code == 200
            assert r.json()["session_id"] == sid

    def test_no_session_id_generates_one(self, client):
        from agents.executor import AgentResult
        with patch("routes.chat.get_executor") as mock_ge:
            mock_ge.return_value = AsyncMock(
                execute=AsyncMock(return_value=AgentResult(success=True, output="ok"))
            )
            r = client.post("/api/chat/send", json={"message": "hi"})
            assert r.status_code == 200
            assert len(r.json()["session_id"]) > 10


# ---------------------------------------------------------------------------
# Chat streaming — edge cases
# ---------------------------------------------------------------------------

class TestStreamEdgeCases:
    def _stream(self, client, payload):
        return client.post("/api/chat/stream", json=payload, timeout=60)

    def test_stream_returns_sse_content_type(self, client):
        with patch("routes.chat.get_router") as mock_gr:
            async def fake_stream(**kwargs):
                yield "Hello"
                yield " world"
            mock_gr.return_value = MagicMock(stream=fake_stream)
            r = self._stream(client, {"message": "hi", "model": "qwen3:1.7b"})
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]

    def test_stream_emits_start_event(self, client):
        with patch("routes.chat.get_router") as mock_gr:
            async def fake_stream(**kwargs):
                yield "ok"
            mock_gr.return_value = MagicMock(stream=fake_stream)
            r = self._stream(client, {"message": "hi", "model": "qwen3:1.7b"})
            assert '"type": "start"' in r.text or '"type":"start"' in r.text.replace(" ", "")

    def test_stream_emits_end_event(self, client):
        with patch("routes.chat.get_router") as mock_gr:
            async def fake_stream(**kwargs):
                yield "ok"
            mock_gr.return_value = MagicMock(stream=fake_stream)
            r = self._stream(client, {"message": "hi", "model": "qwen3:1.7b"})
            assert '"type": "end"' in r.text or '"type":"end"' in r.text.replace(" ", "")

    def test_stream_fallback_on_error(self, client):
        with patch("routes.chat.get_router") as mock_gr:
            async def broken_stream(**kwargs):
                raise RuntimeError("provider down")
                yield  # pragma: no cover
            mock_gr.return_value = MagicMock(stream=broken_stream)
            # The route should fall back to generate() or emit error
            r = self._stream(client, {"message": "hi", "model": "qwen3:1.7b"})
            assert r.status_code == 200  # SSE always 200; error inside stream

    def test_stream_missing_message_422(self, client):
        r = self._stream(client, {"model": "qwen3:1.7b"})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Models endpoint
# ---------------------------------------------------------------------------

class TestModels:
    def test_models_is_dict(self, client):
        r = client.get("/api/chat/models")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_models_values_are_lists(self, client):
        data = client.get("/api/chat/models").json()
        for v in data.values():
            assert isinstance(v, list)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class TestHistory:
    def test_history_unknown_session_returns_empty(self, client):
        r = client.get(f"/api/chat/history/{uuid.uuid4().hex}")
        assert r.status_code == 200

    def test_history_then_clear(self, client):
        sid = f"h-{uuid.uuid4().hex[:6]}"
        client.get(f"/api/chat/history/{sid}")
        r = client.delete(f"/api/chat/history/{sid}")
        assert r.status_code == 200

    def test_clear_twice_is_safe(self, client):
        sid = f"c-{uuid.uuid4().hex[:6]}"
        client.delete(f"/api/chat/history/{sid}")
        r = client.delete(f"/api/chat/history/{sid}")
        assert r.status_code == 200

    def test_history_with_special_chars_sid(self, client):
        sid = "session-with-dash_and.dot+plus"
        r = client.get(f"/api/chat/history/{sid}")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Agents endpoint
# ---------------------------------------------------------------------------

class TestAgentsEndpoint:
    def test_agents_is_list(self, client):
        r = client.get("/api/agents/")
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))

    def test_agent_get_unknown_404(self, client):
        r = client.get("/api/agents/does-not-exist-xyz")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# LLM Router — unit
# ---------------------------------------------------------------------------

class TestRouterUnit:
    def test_init_without_keys(self):
        with patch.dict("os.environ", {"OLLAMA_URL": ""}, clear=False):
            r = LLMRouter()
            assert r.providers == {} or isinstance(r.providers, dict)

    def test_get_provider_openai(self):
        r = LLMRouter()
        assert r._get_provider("gpt-4") == "openai"
        assert r._get_provider("gpt-3.5-turbo") == "openai"

    def test_get_provider_anthropic(self):
        r = LLMRouter()
        assert r._get_provider("claude-3-opus") == "anthropic"

    def test_get_provider_ollama(self):
        r = LLMRouter()
        assert r._get_provider("llama3.2") == "ollama"
        assert r._get_provider("qwen3:8b") == "ollama"
        assert r._get_provider("deepseek-r1:14b") == "ollama"

    def test_list_models_shape(self):
        r = LLMRouter()
        models = r.list_models()
        assert isinstance(models, dict)
        for v in models.values():
            assert isinstance(v, list)

    def test_generate_no_providers_raises(self):
        r = LLMRouter()
        r.providers = {}
        with pytest.raises((ValueError, Exception)):
            import asyncio
            asyncio.run(r.generate(model="x", messages=[{"role": "user", "content": "hi"}]))

    def test_stream_no_providers_raises(self):
        r = LLMRouter()
        r.providers = {}
        with pytest.raises((ValueError, Exception)):
            async def consume():
                async for _ in r.stream(model="x", messages=[]):
                    pass
            import asyncio
            asyncio.run(consume())


# ---------------------------------------------------------------------------
# Agent executor — unit
# ---------------------------------------------------------------------------

class TestExecutorUnit:
    def test_result_defaults(self):
        res = AgentResult(success=True, output="ok")
        assert res.tool_calls == []
        assert res.error is None

    def test_result_failure(self):
        res = AgentResult(success=False, output="", error="boom")
        assert res.success is False
        assert res.error == "boom"

    def test_executor_singleton(self):
        e1 = get_executor()
        e2 = get_executor()
        assert e1 is e2


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class TestMemory:
    def test_memory_singleton(self):
        m1 = get_memory()
        m2 = get_memory()
        assert m1 is m2

    async def test_add_and_get_history(self):
        mem = ConversationMemory()
        sid = f"m-{uuid.uuid4().hex[:6]}"
        await mem.add(sid, "user", "hello", embedding=[0.0] * 4)
        await mem.add(sid, "assistant", "hi", embedding=[0.0] * 4)
        hist = await mem.get_history(sid)
        assert len(hist) >= 2

    async def test_clear_session(self):
        mem = ConversationMemory()
        sid = f"cl-{uuid.uuid4().hex[:6]}"
        await mem.add(sid, "user", "x", embedding=[0.0] * 4)
        await mem.clear_session(sid)
        assert len(await mem.get_history(sid)) == 0

    async def test_unknown_session_empty(self):
        mem = ConversationMemory()
        assert await mem.get_history(uuid.uuid4().hex) == []

    async def test_history_isolation_between_sessions(self):
        mem = ConversationMemory()
        a = f"a-{uuid.uuid4().hex[:6]}"
        b = f"b-{uuid.uuid4().hex[:6]}"
        await mem.add(a, "user", "for-a", embedding=[0.0] * 4)
        hist_b = await mem.get_history(b)
        assert all(m.get("content") != "for-a" for m in hist_b)
