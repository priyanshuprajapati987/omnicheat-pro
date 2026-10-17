"""Chat routes - REST + SSE with Memory & Tools"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from llm.router import get_router
from agents.executor import get_executor
from memory.vector_store import get_memory
import json
import uuid

router = APIRouter()

PROVIDER_HINT = "Configure a provider in .env or use an Ollama model"


def _provider_for_model(model: str) -> str:
    try:
        return get_router()._get_provider(model)
    except Exception:
        return "unknown"

class ChatMessage(BaseModel):
    role: str  # "user", "assistant", "system"
    content: str
    model: str = "gpt-3.5-turbo"

class ChatRequest(BaseModel):
    message: str
    model: str = "gpt-3.5-turbo"
    session_id: Optional[str] = None
    agent_type: str = "general"
    temperature: float = 0.7

class ChatResponse(BaseModel):
    content: str
    model: str
    provider: str
    session_id: str
    tokens_used: int = 0
    tool_calls: List[str] = []


@router.post("/send", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """Send a message and get response (non-streaming)"""
    
    # Generate session ID if not provided
    session_id = request.session_id or str(uuid.uuid4())
    
    # Use agent executor for tool support + memory
    executor = get_executor()
    try:
        result = await executor.execute(
            agent_type=request.agent_type,
            message=request.message,
            session_id=session_id,
            model=request.model,
        )
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={
                "error": str(e) or type(e).__name__,
                "provider": _provider_for_model(request.model),
                "hint": PROVIDER_HINT,
            },
        )
    
    return ChatResponse(
        content=result.output,
        model=request.model,
        provider="agent",
        session_id=session_id,
        tokens_used=result.tokens_used,
        tool_calls=result.tool_calls,
    )


@router.get("/models")
async def list_models():
    """List available models"""
    router_instance = get_router()
    return router_instance.list_models()


@router.post("/stream")
async def stream_message(request: ChatRequest):
    """Stream response token-by-token via Server-Sent Events"""
    session_id = request.session_id or str(uuid.uuid4())
    router_instance = get_router()

    # Build system prompt from agent type
    system_prompts = {
        "general": "You are a helpful AI assistant. Be concise and clear.",
        "coder": "You are an expert programmer. Help users write, debug, and understand code. Use markdown code blocks with language specification.",
        "researcher": "You are a research expert. Help users research topics, find sources, and summarize information with evidence.",
        "writer": "You are a professional writer. Help users create high-quality content with clear structure.",
    }
    system_prompt = system_prompts.get(request.agent_type, system_prompts["general"])

    # Pull recent history from memory for context (chronological, oldest -> newest)
    memory = get_memory()
    history_entries = await memory.get_history(session_id, limit=10)
    messages = [{"role": "system", "content": system_prompt}]
    for e in history_entries:
        messages.append({"role": e.role, "content": e.content})
    messages.append({"role": "user", "content": request.message})

    async def event_generator():
        # Send session metadata first
        yield f"data: {json.dumps({'type': 'start', 'session_id': session_id, 'model': request.model})}\n\n"

        full_response = []
        try:
            async for token in router_instance.stream(
                model=request.model,
                messages=messages,
                temperature=request.temperature,
            ):
                full_response.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        except Exception:
            # Fallback: non-streaming generate
            try:
                response = await router_instance.generate(
                    model=request.model,
                    messages=messages,
                    temperature=request.temperature,
                )
                # Simulate streaming for fallback
                content = response.content
                words = content.split(" ")
                for i, word in enumerate(words):
                    chunk = word + (" " if i < len(words) - 1 else "")
                    full_response.append(chunk)
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
            except Exception as e2:
                yield f"data: {json.dumps({'type': 'error', 'content': str(e2)})}\n\n"
                return

        # Save to memory
        final_text = "".join(full_response)
        try:
            from memory.vector_store import get_embedder
            embedder = get_embedder()
            user_emb = await embedder.embed(request.message)
            asst_emb = await embedder.embed(final_text)
            await memory.add(session_id, "user", request.message, embedding=user_emb)
            await memory.add(session_id, "assistant", final_text, embedding=asst_emb)
        except Exception:
            pass

        yield f"data: {json.dumps({'type': 'end', 'session_id': session_id, 'model': request.model})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history/{session_id}")
async def get_history(session_id: str, limit: int = 20):
    """Get conversation history for a session (newest first)"""
    memory = get_memory()
    entries = await memory.get_history(session_id, limit=limit)
    
    return {
        "session_id": session_id,
        "messages": [
            {
                "role": e.role,
                "content": e.content,
                "created_at": e.created_at,
            }
            for e in reversed(entries)
        ],
    }


@router.delete("/history/{session_id}")
async def clear_history(session_id: str):
    """Clear conversation history for a session"""
    memory = get_memory()
    await memory.clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}
