"""Agents routes"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

class AgentConfig(BaseModel):
    name: str
    description: str
    system_prompt: str
    model: str = "gpt-3.5-turbo"
    tools: List[str] = []

class AgentResponse(BaseModel):
    id: str
    name: str
    description: str
    model: str
    tools: List[str]

# In-memory agent storage (will move to DB in Week 2)
agents_db = {
    "coder": AgentConfig(
        name="Coder",
        description="Expert coding assistant",
        system_prompt="You are an expert programmer. Help users write, debug, and understand code.",
        model="gpt-4",
        tools=["code_execution", "file_ops", "web_search"],
    ),
    "researcher": AgentConfig(
        name="Researcher",
        description="Research and analysis expert",
        system_prompt="You are a research expert. Help users research topics, find sources, and summarize information.",
        model="gpt-4",
        tools=["web_search", "file_ops"],
    ),
    "writer": AgentConfig(
        name="Writer",
        description="Content creation expert",
        system_prompt="You are a professional writer. Help users create high-quality content.",
        model="gpt-3.5-turbo",
        tools=["web_search", "file_ops"],
    ),
}


@router.get("/")
async def list_agents():
    """List all available agents"""
    return {
        "agents": [
            {
                "id": agent_id,
                "name": config.name,
                "description": config.description,
                "model": config.model,
                "tools": config.tools,
            }
            for agent_id, config in agents_db.items()
        ]
    }


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent by ID"""
    if agent_id not in agents_db:
        return {"error": "Agent not found"}
    
    config = agents_db[agent_id]
    return {
        "id": agent_id,
        "name": config.name,
        "description": config.description,
        "system_prompt": config.system_prompt,
        "model": config.model,
        "tools": config.tools,
    }
