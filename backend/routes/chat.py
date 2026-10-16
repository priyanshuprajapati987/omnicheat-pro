"""Chat routes - WebSocket + REST with Memory & Tools"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List, Optional
from llm.router import get_router
from agents.executor import get_executor
from memory.vector_store import get_memory
import json
import uuid

router = APIRouter()

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
    result = await executor.execute(
        agent_type=request.agent_type,
        message=request.message,
        session_id=session_id,
        model=request.model,
    )
    
    return ChatResponse(
        content=result.output,
        model=request.model,
        provider="agent",
        session_id=session_id,
        tool_calls=result.tool_calls,
    )


@router.get("/models")
async def list_models():
    """List available models"""
    router_instance = get_router()
    return router_instance.list_models()


@router.get("/history/{session_id}")
async def get_history(session_id: str, limit: int = 20):
    """Get conversation history for a session"""
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


@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket):
    """WebSocket for streaming chat"""
    await websocket.accept()
    router_instance = get_router()
    executor = get_executor()
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            message = data.get("message", "")
            model = data.get("model", "gpt-3.5-turbo")
            session_id = data.get("session_id", str(uuid.uuid4()))
            agent_type = data.get("agent_type", "general")
            
            if not message:
                await websocket.send_json({"type": "error", "content": "No message provided"})
                continue
            
            # Send start event
            await websocket.send_json({
                "type": "start",
                "model": model,
                "session_id": session_id,
            })
            
            # Execute with agent (includes memory + tools)
            result = await executor.execute(
                agent_type=agent_type,
                message=message,
                session_id=session_id,
                model=model,
            )
            
            # Send response (simulated streaming - in production use real streaming)
            # For now, send the complete response
            await websocket.send_json({
                "type": "token",
                "content": result.output,
            })
            
            # Send completion
            await websocket.send_json({
                "type": "end",
                "content": result.output,
                "tool_calls": result.tool_calls,
                "session_id": session_id,
            })
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"type": "error", "content": str(e)})
