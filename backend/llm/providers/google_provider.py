"""Google Gemini Provider"""

import os
from typing import AsyncGenerator
import google.generativeai as genai
from llm.router import LLMResponse


class GoogleProvider:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")
        genai.configure(api_key=api_key)
    
    async def generate(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate response from Google Gemini"""
        # Convert messages to Gemini format
        system_prompt = ""
        chat_history = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            elif msg["role"] == "user":
                chat_history.append({"role": "user", "parts": [msg["content"]]})
            elif msg["role"] == "assistant":
                chat_history.append({"role": "model", "parts": [msg["content"]]})
        
        # Create model instance
        gemini_model = genai.GenerativeModel(
            model_name=model,
            system_instruction=system_prompt if system_prompt else None,
        )
        
        # Generate response
        response = await gemini_model.generate_content_async(
            chat_history[-1]["parts"][0] if chat_history else "",
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )
        
        return LLMResponse(
            content=response.text,
            model=model,
            provider="google",
            tokens_used=response.usage_metadata.total_token_count if response.usage_metadata else 0,
            finish_reason="stop",
        )
    
    async def stream(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Stream response from Google Gemini"""
        # Google streaming is not yet implemented in async
        # Fall back to non-streaming
        response = await self.generate(model, messages, temperature)
        yield response.content
