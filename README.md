# OmniChat Pro

**Self-hosted, multi-model AI chat** — agents, persistent memory, streaming, and tools. A private alternative to ChatGPT.

[![CI](https://github.com/priyanshuprajapati987/omnicheat-pro/actions/workflows/ci.yml/badge.svg)](https://github.com/priyanshuprajapati987/omnicheat-pro/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![React 18](https://img.shields.io/badge/react-18-61dafb.svg)](https://reactjs.org)
[![Tests](https://img.shields.io/badge/tests-135%20passing-brightgreen.svg)](#-tests)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## Highlights

- **Multi-model** — OpenAI, Anthropic, Google, and Ollama (local). Auto-detects whichever provider you configure.
- **Streaming responses** — SSE streaming with live token output and stop-generation support.
- **AI agents** — specialized agents (Coder, Researcher, Writer) with tool access.
- **Persistent memory** — conversations recalled across sessions via Qdrant vector store (in-memory fallback included).
- **Tools** — web search, code execution, file operations.
- **Session sidebar** — switch between conversations, history saved locally (capped at 50 sessions).
- **Code blocks** — syntax highlighting with one-click copy.
- **Security layer** — rate limiting, input sanitization, and optional API-key auth built in.
- **Self-hosted** — Docker deployment; your data never leaves your machine.

---

## Quick Start

### Option 1: Docker (recommended)

```bash
git clone https://github.com/priyanshuprajapati987/omnicheat-pro.git
cd omnicheat-pro

cp .env.example .env   # add your API keys (or just OLLAMA_URL for local-only)

docker-compose up -d
# Frontend: http://localhost:3000  |  API: http://localhost:8000
```

### Option 2: Manual setup

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate          # Windows (use `source venv/bin/activate` on macOS/Linux)
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install

# Terminal 1 — backend (port 8000)
cd backend && uvicorn main:app --reload --port 8000

# Terminal 2 — frontend (port 3000)
cd frontend && npm run dev
```

> **Local-only?** You need nothing but [Ollama](https://ollama.com). Set `OLLAMA_URL=http://localhost:11434` in `.env` and skip the API keys.

---

## Configuration

```env
# LLM providers — at least one required
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
OLLAMA_URL=http://localhost:11434

# Vector memory (optional — falls back to in-memory store)
QDRANT_URL=http://localhost:6333

# Security (optional)
OMNICHAT_API_KEY=            # enable API-key auth when set
RATE_LIMIT_CAPACITY=30       # burst size per client
RATE_LIMIT_REFILL=0.5        # tokens per second
OMNICHAT_CORS_ORIGINS=http://localhost:3000,http://localhost:5173
TRUSTED_PROXIES=127.0.0.1,::1  # proxies allowed to set X-Forwarded-For
```

---

## Security

The backend ships a middleware layer (`backend/security.py`) that is on by default:

| Control | Behavior |
|---------|----------|
| **Rate limiting** | Token-bucket per client — default burst 30, refill 0.5/s (env-configurable). Proxy-aware: `X-Forwarded-For`/`X-Real-IP` are honored only when the direct peer is in `TRUSTED_PROXIES`; idle buckets are pruned. Exceeding it returns `429`. |
| **Input sanitization** | Every JSON body is scrubbed of XSS (`<script>`/`<iframe>`), SQL injection keywords, path traversal (`../`), and null bytes. `message` fields are capped at 8,000 chars. |
| **API-key auth** | Off by default. Set `OMNICHAT_API_KEY` to require `x-api-key: <key>` or `Authorization: Bearer <key>` on all non-public routes (`/health`, `/docs` stay open). Constant-time comparison. |
| **CORS** | Explicit origin allowlist — no wildcard. Configure via `OMNICHAT_CORS_ORIGINS`. |

---

## API

Interactive docs while running:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

Key endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/chat/send` | Send a message, get a reply (502 + `{error, provider, hint}` if the provider fails) |
| `GET`  | `/api/chat/models` | List available models |
| `GET`  | `/api/chat/history/{session_id}` | Conversation history (newest first) |
| `DELETE` | `/api/chat/history/{session_id}` | Clear a session's history |
| `POST` | `/api/chat/stream` | **SSE streaming** reply |
| `GET`  | `/api/agents/` | List agents |

### Streaming example

```bash
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "model": "qwen3:8b"}'
```

---

## Tests

```bash
cd backend
python -m pytest -q
```

**135 tests passing** across four suites:

| Suite | Count | Covers |
|-------|-------|--------|
| `test_api.py` | 27 | health, chat send/models/history, agents, router, executor, memory |
| `test_security.py` | 37 | sanitizer, token-bucket, rate limiter, API-key auth, middleware |
| `test_edge_cases.py` | 39 | chat/stream edge cases, long/invalid input, memory, executor, router |
| `test_regressions.py` | 32 | history ordering, provider fallback, 502 shape, tokens_used, Gemini history, async web search, 384-dim embeds, Qdrant fallbacks, proxy-aware client IP, rate-limiter pruning |

CI runs lint (`ruff`) + the full suite + a frontend build on every push.

---

## Built-in Agents

| Agent | Purpose | Tools |
|-------|---------|-------|
| **Coder** | Write, debug, execute code | code_execution, file_ops, web_search |
| **Researcher** | Research topics, summarize | web_search, file_ops |
| **Writer** | Content creation | web_search, file_ops |

---

## Project Structure

```
omnicheat-pro/
├── backend/
│   ├── main.py           # App entry + middleware wiring
│   ├── security.py       # Rate limit / sanitizer / auth
│   ├── routes/           # API routes (chat, agents, health)
│   ├── agents/           # Agent executor
│   ├── llm/              # Multi-provider router
│   ├── memory/           # Vector conversation memory
│   └── tools/            # Web search, code exec, files
├── frontend/             # React 18 + Vite + Tailwind
└── docker-compose.yml
```

---

## Tech Stack

- **Backend:** Python, FastAPI, SSE
- **Frontend:** React 18, Vite, Tailwind CSS, TanStack Query, Zustand
- **Vector DB:** Qdrant (in-memory fallback)
- **LLM:** OpenAI, Anthropic, Google, Ollama

---

## License

MIT License — see [LICENSE](LICENSE)

## Credits

Inspired by [G0DM0D3](https://github.com/elder-plinius/G0DM0D3) — rebuilt with agents, memory, streaming, and a security layer.

---

**Built with ❤️ by [Priyanshu](https://github.com/priyanshuprajapati987)**
