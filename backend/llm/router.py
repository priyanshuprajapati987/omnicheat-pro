"""Multi-Provider LLM Router"""

import os
from typing import Optional, AsyncGenerator
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    tokens_used: int = 0
    finish_reason: str = "stop"


class LLMRouter:
    """Route requests to multiple LLM providers"""
    
    def __init__(self):
        self.providers = {}
        self._init_providers()
    
    def _init_providers(self):
        """Initialize available providers based on API keys"""
        if os.getenv("OPENAI_API_KEY"):
            from llm.providers.openai_provider import OpenAIProvider
            self.providers["openai"] = OpenAIProvider()
        
        if os.getenv("ANTHROPIC_API_KEY"):
            from llm.providers.anthropic_provider import AnthropicProvider
            self.providers["anthropic"] = AnthropicProvider()
        
        if os.getenv("OLLAMA_URL"):
            from llm.providers.ollama_provider import OllamaProvider
            self.providers["ollama"] = OllamaProvider()
        
        if os.getenv("GOOGLE_API_KEY"):
            from llm.providers.google_provider import GoogleProvider
            self.providers["google"] = GoogleProvider()
    
    async def generate(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> LLMResponse:
        """Generate response from specified model"""
        provider = self._resolve_provider(model)
        return await provider.generate(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    
    async def stream(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Stream response token by token"""
        provider = self._resolve_provider(model)
        async for token in provider.stream(model=model, messages=messages, temperature=temperature):
            yield token
    
    def _resolve_provider(self, model: str):
        """Pick the provider for a model, falling back to the first configured one"""
        provider_name = self._get_provider(model)
        
        if provider_name in self.providers:
            return self.providers[provider_name]
        
        if self.providers:
            return next(iter(self.providers.values()))
        
        raise ValueError(f"Provider not available: {provider_name}")
    
    def _get_provider(self, model: str) -> str:
        """Extract provider from model name"""
        model_lower = model.lower()
        
        # OpenAI models
        if model_lower.startswith(("gpt-", "o1", "o3", "chatgpt")):
            return "openai"
        # Anthropic models
        elif model_lower.startswith(("claude", "anthropic")):
            return "anthropic"
        # Google models
        elif model_lower.startswith(("gemini", "palm")):
            return "google"
        # Ollama models (local) - check common local model names
        elif any(x in model_lower for x in ["llama", "mistral", "qwen", "codellama", "phi", "gemma", "deepseek", "spark"]):
            return "ollama"
        # Default to ollama for unknown models (local fallback)
        elif "ollama" in self.providers:
            return "ollama"
        
        return "openai"
    
    def list_models(self) -> dict:
        """List all available models"""
        models = {
            "openai": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
            "anthropic": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
            "google": ["gemini-pro", "gemini-pro-vision"],
            "ollama": ["llama2", "mistral", "codellama"],
        }
        
        # Filter to only available providers
        available = {}
        for provider, model_list in models.items():
            if provider in self.providers:
                available[provider] = model_list
        
        return available


# Singleton
_router: Optional[LLMRouter] = None

def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
