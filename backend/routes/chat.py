"""Chat routes - WebSocket + REST"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List, Optional
from llm.router import get_router
import json

router = APIRouter()

class ChatMessage(BaseModel):
    role: str  # "user", "assistant", "system"
    content: str
    model: str = "gpt-3.5-turbo"

class ChatRequest(BaseModel):
    message: str
    model: str = "gpt-3.5-turbo"
    history: List[ChatMessage] = []
    temperature: float = 0.7

class ChatResponse(BaseModel):
    content: str
    model: str
    provider: str
    tokens_used: int = 0


@router.post("/send", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """Send a message and get response (non-streaming)"""
    router_instance = get_router()
    
    # Build messages
    messages = [{"role": m.role, "content": m.content} for m in request.history]
    messages.append({"role": "user", "content": request.message})
    
    # Generate response
    response = await router_instance.generate(
        model=request.model,
        messages=messages,
        temperature=request.temperature,
    )
    
    return ChatResponse(
        content=response.content,
        model=response.model,
        provider=response.provider,
        tokens_used=response.tokens_used,
    )


@router.get("/models")
async def list_models():
    """List available models"""
    router_instance = get_router()
    return router_instance.list_models()


@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket):
    """WebSocket for streaming chat"""
    await websocket.accept()
    router_instance = get_router()
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            message = ChatMessage(**data)
            
            # Build history
            messages = [{"role": m.role, "content": m.content} for m in data.get("history", [])]
            messages.append({"role": "user", "content": message.content})
            
            # Stream response
            await websocket.send_json({"type": "start", "model": message.model})
            
            full_response = ""
            async for token in router_instance.stream(
                model=message.model,
                messages=messages,
                temperature=message.temperature if hasattr(message, 'temperature') else 0.7,
            ):
                full_response += token
                await websocket.send_json({"type": "token", "content": token})
            
            # Send completion
            await websocket.send_json({
                "type": "end",
                "content": full_response,
            })
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"type": "error", "content": str(e)})
