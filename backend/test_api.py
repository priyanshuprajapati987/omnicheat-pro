"""OmniChat Pro Backend API Tests

Tests cover health, chat, agents, and LLM router endpoints with mocked LLM.
Run: cd backend && python -m pytest test_api.py -v
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# Patch heavy providers before importing app
with patch.dict("os.environ", {"OLLAMA_URL": ""}, clear=False):
    from main import app
    from llm.router import LLMRouter, LLMResponse
    from agents.executor import AgentExecutor, AgentResult
    from memory.vector_store import get_memory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_llm_response():
    return LLMResponse(
        content="Hello from mock LLM!",
        model="qwen3:1.7b",
        provider="ollama",
        tokens_used=12,
    )


@pytest.fixture
def mock_agent_result():
    return AgentResult(
        success=True,
        output="Agent response with tools.",
        tool_calls=["web_search"],
    )


# ---------------------------------------------------------------------------
# Health / Root
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_endpoint(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_root_endpoint(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "OmniChat Pro API"
        assert data["status"] == "running"


# ---------------------------------------------------------------------------
# Chat Endpoints (mocked executor)
# ---------------------------------------------------------------------------

class TestChatSend:
    def test_send_message_returns_response(self, client, mock_agent_result):
        with patch("routes.chat.get_executor") as mock_ge:
            mock_ge.return_value = AsyncMock(execute=AsyncMock(return_value=mock_agent_result))
            r = client.post(
                "/api/chat/send",
                json={"message": "hello", "model": "qwen3:1.7b", "agent_type": "general"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data["content"] == mock_agent_result.output
        assert data["session_id"]
        assert data["tool_calls"] == ["web_search"]

    def test_send_message_generates_session_id(self, client, mock_agent_result):
        with patch("routes.chat.get_executor") as mock_ge:
            mock_ge.return_value = AsyncMock(execute=AsyncMock(return_value=mock_agent_result))
            r1 = client.post("/api/chat/send", json={"message": "a"})
            r2 = client.post("/api/chat/send", json={"message": "b"})
        sid1 = r1.json()["session_id"]
        sid2 = r2.json()["session_id"]
        assert sid1 != sid2  # distinct sessions

    def test_send_message_passes_session_id(self, client, mock_agent_result):
        sid = "test-session-123"
        with patch("routes.chat.get_executor") as mock_ge:
            mock_exec = AsyncMock(execute=AsyncMock(return_value=mock_agent_result))
            mock_ge.return_value = mock_exec
            r = client.post(
                "/api/chat/send",
                json={"message": "hi", "session_id": sid},
            )
        assert r.json()["session_id"] == sid
        call_kwargs = mock_exec.execute.call_args
        assert call_kwargs.kwargs.get("session_id") == sid or call_kwargs[1].get("session_id") == sid

    def test_send_message_invalid_body(self, client):
        r = client.post("/api/chat/send", json={})
        assert r.status_code == 422  # missing required "message"


class TestChatModels:
    def test_list_models(self, client):
        with patch("routes.chat.get_router") as mock_gr:
            mock_gr.return_value = MagicMock(list_models=MagicMock(return_value={
                "ollama": ["qwen3:1.7b", "llama3.2"],
            }))
            r = client.get("/api/chat/models")
        assert r.status_code == 200
        data = r.json()
        assert "ollama" in data
        assert "qwen3:1.7b" in data["ollama"]


class TestChatHistory:
    def test_get_history_empty(self, client):
        sid = str(uuid.uuid4())
        with patch("routes.chat.get_memory") as mock_gm:
            mock_mem = AsyncMock()
            mock_mem.get_history = AsyncMock(return_value=[])
            mock_gm.return_value = mock_mem
            r = client.get(f"/api/chat/history/{sid}")
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"] == sid
        assert data["messages"] == []

    def test_get_history_with_entries(self, client):
        from memory.vector_store import MemoryEntry
        sid = str(uuid.uuid4())
        entries = [
            MemoryEntry(id="1", session_id=sid, role="user", content="hi"),
            MemoryEntry(id="2", session_id=sid, role="assistant", content="hello!"),
        ]
        with patch("routes.chat.get_memory") as mock_gm:
            mock_mem = AsyncMock()
            mock_mem.get_history = AsyncMock(return_value=entries)
            mock_gm.return_value = mock_mem
            r = client.get(f"/api/chat/history/{sid}")
        data = r.json()
        assert len(data["messages"]) == 2
        # route returns reversed(entries) → newest first
        assert data["messages"][0]["role"] == "assistant"
        assert data["messages"][1]["role"] == "user"

    def test_clear_history(self, client):
        sid = str(uuid.uuid4())
        with patch("routes.chat.get_memory") as mock_gm:
            mock_mem = AsyncMock()
            mock_mem.clear_session = AsyncMock()
            mock_gm.return_value = mock_mem
            r = client.delete(f"/api/chat/history/{sid}")
        assert r.status_code == 200
        assert r.json()["status"] == "cleared"
        mock_mem.clear_session.assert_called_once()


# ---------------------------------------------------------------------------
# Streaming Endpoint (SSE)
# ---------------------------------------------------------------------------

class TestChatStream:
    def test_stream_returns_sse(self, client):
        async def fake_stream(model, messages, temperature=0.7):
            yield "Hello "
            yield "streaming "
            yield "world!"

        with patch("routes.chat.get_router") as mock_gr, \
             patch("routes.chat.get_memory") as mock_gm:
            mock_router = MagicMock()
            mock_router.stream = fake_stream
            mock_gr.return_value = mock_router
            mock_mem = AsyncMock()
            mock_mem.get_history = AsyncMock(return_value=[])
            mock_mem.add = AsyncMock()
            mock_gm.return_value = mock_mem

            r = client.post(
                "/api/chat/stream",
                json={"message": "hi", "model": "qwen3:1.7b", "session_id": "s-test"},
            )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        body = r.text
        assert '"type": "start"' in body or '"type":"start"' in body
        assert "Hello" in body
        assert "streaming" in body
        assert "world!" in body
        assert '"type": "end"' in body or '"type":"end"' in body

    def test_stream_fallback_to_generate(self, client):
        """When stream() raises, falls back to generate()"""
        from llm.router import LLMResponse

        async def broken_stream(model, messages, temperature=0.7):
            raise RuntimeError("stream unsupported")
            yield ""  # pragma: no cover

        with patch("routes.chat.get_router") as mock_gr, \
             patch("routes.chat.get_memory") as mock_gm:
            mock_router = MagicMock()
            mock_router.stream = broken_stream
            mock_router.generate = AsyncMock(return_value=LLMResponse(
                content="Fallback response here",
                model="qwen3:1.7b",
                provider="ollama",
            ))
            mock_gr.return_value = mock_router
            mock_mem = AsyncMock()
            mock_mem.get_history = AsyncMock(return_value=[])
            mock_mem.add = AsyncMock()
            mock_gm.return_value = mock_mem

            r = client.post(
                "/api/chat/stream",
                json={"message": "hi", "model": "qwen3:1.7b", "session_id": "s-fb"},
            )
        assert r.status_code == 200
        assert "Fallback" in r.text

    def test_stream_sends_session_id(self, client):
        async def fake_stream(model, messages, temperature=0.7):
            yield "ok"

        with patch("routes.chat.get_router") as mock_gr, \
             patch("routes.chat.get_memory") as mock_gm:
            mock_router = MagicMock()
            mock_router.stream = fake_stream
            mock_gr.return_value = mock_router
            mock_mem = AsyncMock()
            mock_mem.get_history = AsyncMock(return_value=[])
            mock_mem.add = AsyncMock()
            mock_gm.return_value = mock_mem

            r = client.post(
                "/api/chat/stream",
                json={"message": "hi", "model": "qwen3:1.7b", "session_id": "my-sid-42"},
            )
        assert "my-sid-42" in r.text


# ---------------------------------------------------------------------------
# Agents Endpoints
# ---------------------------------------------------------------------------

class TestAgents:
    def test_list_agents(self, client):
        r = client.get("/api/agents/")
        assert r.status_code == 200
        data = r.json()
        agents = data["agents"]
        assert isinstance(agents, list)
        assert len(agents) >= 3  # coder, researcher, writer
        ids = [a["id"] for a in agents]
        assert "coder" in ids
        assert "researcher" in ids
        assert "writer" in ids

    def test_list_agents_shape(self, client):
        r = client.get("/api/agents/")
        for agent in r.json()["agents"]:
            assert "id" in agent
            assert "name" in agent
            assert "description" in agent
            assert "model" in agent
            assert "tools" in agent

    def test_get_agent_found(self, client):
        r = client.get("/api/agents/coder")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "coder"
        assert data["name"] == "Coder"
        assert "system_prompt" in data
        assert "code_execution" in data["tools"]

    def test_get_agent_not_found(self, client):
        r = client.get("/api/agents/nonexistent")
        assert r.status_code == 200  # returns error dict
        data = r.json()
        assert data["error"] == "Agent not found"


# ---------------------------------------------------------------------------
# LLM Router (unit)
# ---------------------------------------------------------------------------

class TestLLMRouter:
    def test_router_init_without_keys(self):
        with patch.dict("os.environ", {
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "OLLAMA_URL": "",
            "GOOGLE_API_KEY": "",
        }):
            router = LLMRouter()
            assert router.providers == {}

    def test_get_provider_openai(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test", "OLLAMA_URL": ""}):
            router = LLMRouter()
            assert router._get_provider("gpt-4") == "openai"
            assert router._get_provider("gpt-3.5-turbo") == "openai"

    def test_get_provider_anthropic(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test", "OLLAMA_URL": ""}):
            router = LLMRouter()
            assert router._get_provider("claude-3-opus") == "anthropic"

    def test_get_provider_ollama(self):
        with patch.dict("os.environ", {"OLLAMA_URL": "http://127.0.0.1:11434"}):
            router = LLMRouter()
            assert router._get_provider("llama3.2") == "ollama"
            assert router._get_provider("qwen3:8b") == "ollama"
            assert router._get_provider("deepseek-r1:14b") == "ollama"

    def test_list_models_empty_when_no_providers(self):
        with patch.dict("os.environ", {
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "OLLAMA_URL": "",
            "GOOGLE_API_KEY": "",
        }):
            router = LLMRouter()
            assert router.list_models() == {}

    def test_list_models_ollama(self):
        with patch.dict("os.environ", {"OLLAMA_URL": "http://127.0.0.1:11434"}):
            router = LLMRouter()
            models = router.list_models()
            assert "ollama" in models


# ---------------------------------------------------------------------------
# Agent Executor (unit, mocked router)
# ---------------------------------------------------------------------------

class TestAgentExecutor:
    @pytest.mark.asyncio
    async def test_execute_simple_chat(self):
        mock_response = LLMResponse(content="Hi!", model="qwen3:1.7b", provider="ollama")
        with patch("agents.executor.get_router") as mock_gr, \
             patch("agents.executor.get_memory") as mock_gm, \
             patch("agents.executor.get_embedder") as mock_ge, \
             patch("agents.executor.get_tool_registry") as mock_gt:
            mock_router = AsyncMock(generate=AsyncMock(return_value=mock_response))
            mock_gr.return_value = mock_router
            mock_mem = AsyncMock()
            mock_mem.get_history = AsyncMock(return_value=[])
            mock_mem.add = AsyncMock()
            mock_gm.return_value = mock_mem
            mock_ge.return_value = MagicMock()
            mock_ge.return_value.embed = AsyncMock(return_value=[0.0] * 384)
            mock_gt.return_value = MagicMock(has_tool=MagicMock(return_value=False))

            executor = AgentExecutor()
            result = await executor.execute(
                agent_type="general",
                message="hello",
                session_id="s1",
                model="qwen3:1.7b",
            )
        assert result.success is True
        assert result.output == "Hi!"

    @pytest.mark.asyncio
    async def test_executor_dataclass_defaults(self):
        r = AgentResult(success=True, output="ok")
        assert r.tool_calls == []
        assert r.error is None


# ---------------------------------------------------------------------------
# Memory (in-memory fallback)
# ---------------------------------------------------------------------------

class TestMemoryFallback:
    @pytest.mark.asyncio
    async def test_add_and_get_history(self):
        from memory.vector_store import ConversationMemory
        with patch.object(ConversationMemory, "_ensure_collection", lambda self: None):
            mem = ConversationMemory()
            mem.client = None
            mem._connected = False
            emb = [0.0] * 384
            await mem.add("sess-x", "user", "hello world", embedding=emb)
            await mem.add("sess-x", "assistant", "hi there", embedding=emb)
            entries = await mem.get_history("sess-x")
        assert len(entries) == 2
        assert entries[0].role == "user"
        assert entries[1].role == "assistant"

    @pytest.mark.asyncio
    async def test_clear_session(self):
        from memory.vector_store import ConversationMemory
        with patch.object(ConversationMemory, "_ensure_collection", lambda self: None):
            mem = ConversationMemory()
            mem.client = None
            mem._connected = False
            await mem.add("sess-y", "user", "msg", embedding=[0.0] * 384)
            await mem.clear_session("sess-y")
            entries = await mem.get_history("sess-y")
        assert entries == []
