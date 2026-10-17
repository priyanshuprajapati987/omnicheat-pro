"""OmniChat Pro - FastAPI Backend"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import chat, agents, health
from security import SecurityMiddleware
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="OmniChat Pro API",
    description="Professional AI Chat - Multi-model, agents, memory, tools",
    version="0.1.0",
)

# CORS — explicit origin allowlist (no wildcard)
_allowed_origins = os.getenv(
    "OMNICHAT_CORS_ORIGINS",
    "http://localhost:3000,http://localhost:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Security: rate limiting + input sanitization + optional API-key auth
app.add_middleware(SecurityMiddleware)

# Routes
app.include_router(health.router, tags=["health"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])


@app.get("/")
async def root():
    return {
        "name": "OmniChat Pro API",
        "version": "0.1.0",
        "status": "running",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
