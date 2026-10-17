"""Tool Integrations for Agents"""

import os
import asyncio
from typing import Optional
from dataclasses import dataclass
from duckduckgo_search import DDGS


@dataclass
class ToolResult:
    success: bool
    output: str
    error: Optional[str] = None


class WebSearchTool:
    """Web search using DuckDuckGo"""
    
    async def search(self, query: str, max_results: int = 5) -> ToolResult:
        """Search the web"""
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                
            if not results:
                return ToolResult(
                    success=False,
                    output="",
                    error="No results found",
                )
            
            formatted = []
            for i, r in enumerate(results, 1):
                formatted.append(f"{i}. {r.get('title', 'No title')}\n"
                               f"   URL: {r.get('href', 'No URL')}\n"
                           f"   {r.get('body', 'No description')}\n")
            
            return ToolResult(
                success=True,
                output="\n".join(formatted),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )


class CodeExecutionTool:
    """Execute code in a sandboxed environment"""
    
    async def execute(self, code: str, language: str = "python") -> ToolResult:
        """Execute code and return output"""
        try:
            if language == "python":
                return await self._execute_python(code)
            elif language in ["javascript", "node"]:
                return await self._execute_javascript(code)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Language not supported: {language}",
                )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
    
    async def _execute_python(self, code: str) -> ToolResult:
        """Execute Python code"""
        # Create a temporary file
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            # Execute with timeout
            process = await asyncio.create_subprocess_exec(
                "python",
                temp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10.0,
            )
            
            if process.returncode == 0:
                return ToolResult(
                    success=True,
                    output=stdout.decode(),
                )
            else:
                return ToolResult(
                    success=False,
                    output=stdout.decode(),
                    error=stderr.decode(),
                )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error="Execution timed out (10s limit)",
            )
        finally:
            os.unlink(temp_path)
    
    async def _execute_javascript(self, code: str) -> ToolResult:
        """Execute JavaScript code"""
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            process = await asyncio.create_subprocess_exec(
                "node",
                temp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10.0,
            )
            
            if process.returncode == 0:
                return ToolResult(
                    success=True,
                    output=stdout.decode(),
                )
            else:
                return ToolResult(
                    success=False,
                    output=stdout.decode(),
                    error=stderr.decode(),
                )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error="Execution timed out (10s limit)",
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="Node.js not installed",
            )
        finally:
            os.unlink(temp_path)


class FileOpsTool:
    """File operations (read, write, list)"""
    
    async def read_file(self, path: str) -> ToolResult:
        """Read file contents"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return ToolResult(success=True, output=content)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
    
    async def write_file(self, path: str, content: str) -> ToolResult:
        """Write content to file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return ToolResult(success=True, output=f"File written to {path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
    
    async def list_directory(self, path: str = '.') -> ToolResult:
        """List directory contents"""
        try:
            items = os.listdir(path)
            formatted = []
            for item in items:
                full_path = os.path.join(path, item)
                if os.path.isdir(full_path):
                    formatted.append(f"📁 {item}/")
                else:
                    size = os.path.getsize(full_path)
                    formatted.append(f"📄 {item} ({size} bytes)")
            
            return ToolResult(success=True, output="\n".join(formatted))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


# Tool Registry
class ToolRegistry:
    """Registry of all available tools"""
    
    def __init__(self):
        self.tools = {
            "web_search": WebSearchTool(),
            "code_execution": CodeExecutionTool(),
            "file_ops": FileOpsTool(),
        }
    
    def get_tool(self, name: str):
        """Get tool by name"""
        return self.tools.get(name)
    
    def list_tools(self) -> list[str]:
        """List all available tools"""
        return list(self.tools.keys())


# Singleton
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
