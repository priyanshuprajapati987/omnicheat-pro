"""Agent Execution Engine"""

from typing import List, Optional
from dataclasses import dataclass, field
from llm.router import get_router
from tools.registry import get_tool_registry
from memory.vector_store import get_memory, get_embedder


@dataclass
class AgentResult:
    success: bool
    output: str
    tool_calls: List[str] = field(default_factory=list)
    error: Optional[str] = None
    tokens_used: int = 0


class AgentExecutor:
    """Execute agents with tool support"""
    
    def __init__(self):
        self.router = get_router()
        self.tools = get_tool_registry()
        self.memory = get_memory()
        self.embedder = get_embedder()
    
    async def execute(
        self,
        agent_type: str,
        message: str,
        session_id: str = "default",
        model: str = "gpt-3.5-turbo",
    ) -> AgentResult:
        """Execute an agent with the given message"""
        
        # Get agent system prompt
        system_prompt = self._get_system_prompt(agent_type)
        
        # Get conversation history from memory
        history = await self._get_history(session_id)
        
        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})
        
        # Check if tools are needed
        tool_calls = []
        if self._needs_tools(message, agent_type):
            # Execute with tool support
            result = await self._execute_with_tools(
                agent_type, message, messages, model, tool_calls
            )
        else:
            # Simple LLM response
            response = await self.router.generate(
                model=model,
                messages=messages,
                temperature=0.7,
            )
            result = AgentResult(
                success=True,
                output=response.content,
                tool_calls=tool_calls,
                tokens_used=response.tokens_used,
            )
        
        # Save to memory
        await self._save_to_memory(session_id, "user", message)
        await self._save_to_memory(session_id, "assistant", result.output)
        
        return result
    
    def _get_system_prompt(self, agent_type: str) -> str:
        """Get system prompt for agent type"""
        prompts = {
            "coder": """You are an expert programmer. You help users write, debug, and understand code.
- When asked to write code, provide complete, working code with explanations
- Use markdown code blocks with language specification
- If tools are available, you can execute code to verify it works
- Always explain your approach""",
            
            "researcher": """You are a research expert. You help users research topics and find information.
- Provide accurate, well-sourced information
- Use web search when available to find current information
- Summarize findings clearly
- Cite sources when possible""",
            
            "writer": """You are a professional writer. You help users create high-quality content.
- Write clear, engaging content
- Adapt tone and style to the audience
- Use proper structure and formatting
- Ask clarifying questions if needed""",
            
            "general": """You are a helpful AI assistant. You provide accurate, useful responses.
- Be concise but thorough
- Ask clarifying questions if needed
- Use markdown for formatting when appropriate""",
        }
        return prompts.get(agent_type, prompts["general"])
    
    async def _get_history(self, session_id: str) -> List[dict]:
        """Get conversation history from memory (chronological, oldest first)"""
        entries = await self.memory.get_history(session_id, limit=10)
        return [
            {"role": e.role, "content": e.content}
            for e in entries
        ]
    
    def _needs_tools(self, message: str, agent_type: str) -> bool:
        """Check if message requires tool usage"""
        message_lower = message.lower()
        
        # Web search keywords
        search_keywords = ["search", "find", "look up", "current", "latest", "news"]
        if any(kw in message_lower for kw in search_keywords):
            return True
        
        # Code execution keywords
        code_keywords = ["run", "execute", "test", "debug", "verify"]
        if any(kw in message_lower for kw in code_keywords):
            return True
        
        # File operation keywords
        file_keywords = ["read file", "write file", "save to", "list files"]
        if any(kw in message_lower for kw in file_keywords):
            return True
        
        return False
    
    async def _execute_with_tools(
        self,
        agent_type: str,
        message: str,
        messages: List[dict],
        model: str,
        tool_calls: List[str],
    ) -> AgentResult:
        """Execute with tool support"""
        
        # Determine which tool to use
        message_lower = message.lower()
        
        # Web search
        if any(kw in message_lower for kw in ["search", "find", "look up", "current", "latest"]):
            query = self._extract_search_query(message)
            if query:
                tool = self.tools.get_tool("web_search")
                result = await tool.search(query)
                tool_calls.append("web_search")
                
                if result.success:
                    # Add tool result to context
                    messages.append({
                        "role": "system",
                        "content": f"Search results:\n{result.output}"
                    })
        
        # Code execution
        elif any(kw in message_lower for kw in ["run", "execute", "test code"]):
            code = self._extract_code(message)
            if code:
                tool = self.tools.get_tool("code_execution")
                lang = self._detect_language(code)
                result = await tool.execute(code, lang)
                tool_calls.append("code_execution")
                
                if result.success:
                    messages.append({
                        "role": "system",
                        "content": f"Code execution output:\n{result.output}"
                    })
        
        # Generate response with tool context
        response = await self.router.generate(
            model=model,
            messages=messages,
            temperature=0.7,
        )
        
        return AgentResult(
            success=True,
            output=response.content,
            tool_calls=tool_calls,
            tokens_used=response.tokens_used,
        )
    
    def _extract_search_query(self, message: str) -> Optional[str]:
        """Extract search query from message"""
        # Remove common prefixes
        prefixes = ["search for ", "search ", "find ", "look up ", "what is the latest "]
        query = message
        for prefix in prefixes:
            if query.lower().startswith(prefix):
                query = query[len(prefix):]
                break
        return query.strip()
    
    def _extract_code(self, message: str) -> Optional[str]:
        """Extract code from message"""
        # Look for code blocks
        if "```" in message:
            parts = message.split("```")
            if len(parts) >= 2:
                return parts[1].strip()
        return None
    
    def _detect_language(self, code: str) -> str:
        """Detect programming language from code"""
        if "def " in code or "import " in code or "print(" in code:
            return "python"
        elif "function " in code or "console.log" in code or "const " in code:
            return "javascript"
        return "python"
    
    async def _save_to_memory(self, session_id: str, role: str, content: str):
        """Save message to memory"""
        embedding = await self.embedder.embed(content)
        await self.memory.add(
            session_id=session_id,
            role=role,
            content=content,
            embedding=embedding,
        )


# Singleton
_executor: Optional[AgentExecutor] = None


def get_executor() -> AgentExecutor:
    global _executor
    if _executor is None:
        _executor = AgentExecutor()
    return _executor
