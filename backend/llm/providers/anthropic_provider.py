"""Anthropic Provider"""

import os
from typing import AsyncGenerator
from anthropic import AsyncAnthropic
from llm.router import LLMResponse


class AnthropicProvider:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = AsyncAnthropic(api_key=api_key)
    
    async def generate(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate response from Anthropic"""
        # Anthropic requires system prompt separately
        system_prompt = ""
        chat_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                chat_messages.append(msg)
        
        response = await self.client.messages.create(
            model=model,
            system=system_prompt if system_prompt else None,
            messages=chat_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        return LLMResponse(
            content=response.content[0].text if response.content else "",
            model=response.model,
            provider="anthropic",
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            finish_reason=response.stop_reason or "end_turn",
        )
    
    async def stream(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Stream response from Anthropic"""
        system_prompt = ""
        chat_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                chat_messages.append(msg)
        
        async with self.client.messages.stream(
            model=model,
            system=system_prompt if system_prompt else None,
            messages=chat_messages,
            temperature=temperature,
            max_tokens=4096,
        ) as stream:
            async for text in stream.text_stream:
                yield text
