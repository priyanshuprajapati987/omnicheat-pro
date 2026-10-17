# OmniChat Pro - Backend

## Setup

```bash
# Create virtual environment
python -m venv venv

# Activate
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Setup env
cp ../.env.example ../.env
# Edit ../.env with your API keys

# Run
uvicorn main:app --reload --port 8000
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Structure

```
backend/
├── main.py           # FastAPI app entry
├── routes/           # API routes
│   ├── health.py     # Health check
│   ├── chat.py       # Chat endpoints + SSE streaming
│   └── agents.py     # Agent management
├── llm/              # LLM providers
│   └── router.py     # Multi-provider router
├── agents/           # Agent implementations (Week 2)
├── memory/           # Conversation memory (Week 2)
└── tools/            # Tool integrations (Week 2)
```
