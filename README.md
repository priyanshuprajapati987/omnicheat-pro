# OmniChat Pro 🚀

**Professional AI Chat** — Multi-model, agents, memory, tools. Self-hosted alternative to ChatGPT.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![React 18](https://img.shields.io/badge/react-18-blue.svg)](https://reactjs.org)

---

## ✨ Features

- 🤖 **Multi-Model** — OpenAI, Anthropic, Ollama, Google, Mistral
- 🧠 **AI Agents** — Specialized agents (Coder, Researcher, Writer)
- 💾 **Persistent Memory** — Remembers conversations (Qdrant vector DB)
- 🛠️ **Tool Usage** — Web search, code execution, file operations
- 🐳 **Self-Hosted** — Docker deployment, your data stays yours
- 🔌 **API Access** — REST API for developers
- 👥 **Team Features** — Shared chats, workspaces

---

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone
git clone https://github.com/priyanshuprajapati987/omnicheat-pro.git
cd omnicheat-pro

# Setup env
cp .env.example .env
# Edit .env with your API keys

# Launch
docker-compose up -d

# Open http://localhost:3000
```

### Option 2: Manual Setup

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install

# Run
# Terminal 1 (Backend):
cd backend && uvicorn main:app --reload --port 8000

# Terminal 2 (Frontend):
cd frontend && npm run dev
```

---

## 📁 Project Structure

```
omnicheat-pro/
├── backend/              # FastAPI backend
│   ├── main.py          # App entry
│   ├── routes/          # API routes
│   ├── agents/          # AI agents
│   ├── llm/             # LLM providers
│   ├── memory/          # Conversation memory
│   └── tools/           # Tool integrations
├── frontend/            # React frontend
├── docker/              # Docker configs
└── docs/                # Documentation
```

---

## 🔧 Configuration

Create `.env` file:

```env
# LLM Providers (at least one required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OLLAMA_URL=http://localhost:11434

# Database
DATABASE_URL=sqlite:///./omnicheat.db

# Vector DB (for memory)
QDRANT_URL=http://localhost:6333

# Auth (optional)
JWT_SECRET=your-secret-key
```

---

## 📖 API Documentation

Once running, visit:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## 🧪 Tests

```bash
cd backend
python -m pytest test_api.py -v
```

**24 tests passing** — health, chat (send/models/history), agents, LLM router, agent executor, memory fallback.

## 🐳 Docker

```bash
docker-compose up -d
# Backend :8000, Frontend :3000
```

## 🤖 Built-in Agents

| Agent | Purpose | Tools |
|-------|---------|-------|
| **Coder** | Write, debug, execute code | code_execution, file_ops, web_search |
| **Researcher** | Research topics, summarize | web_search, file_ops |
| **Writer** | Content creation | web_search, file_ops |

---

## 🛠️ Tech Stack

- **Backend:** Python, FastAPI, WebSockets
- **Frontend:** React 18, Vite, Tailwind CSS
- **Database:** SQLite / PostgreSQL
- **Vector DB:** Qdrant (for memory)
- **LLM:** Multi-provider (OpenAI, Anthropic, Ollama, Google)

---

## 📄 License

MIT License — see [LICENSE](LICENSE)

---

## 🙏 Credits

Inspired by [G0DM0D3](https://github.com/elder-plinius/G0DM0D3) — rebuilt with agents, memory, and better architecture.

---

**Made with ❤️ by [Priyanshu](https://github.com/priyanshuprajapati987)**
