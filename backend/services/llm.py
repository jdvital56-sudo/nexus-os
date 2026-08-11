"""LLM Service — Unified interface for LLM providers.

Supports:
- Ollama (local)
- OpenAI
- Anthropic
- Google Gemini
- Any OpenAI-compatible API
"""
import json
import httpx
import logging
import os
from typing import Optional, List, Dict, Any
from ..core.config import (
    LLM_PROVIDER,
    LLM_MODEL,
    LLM_API_KEY,
    LLM_BASE_URL,
)
from . import budget

logger = logging.getLogger(__name__)


class LLMMessage:
    """Standard message format."""
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content
    
    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class LLMResponse:
    """Standard response format."""
    def __init__(self, content: str, model: str, usage: dict = None):
        self.content = content
        self.model = model
        self.usage = usage or {}
        # Ответ получен сверх дневного бюджета — канал должен предупредить (I-4)
        self.over_budget = False

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "model": self.model,
            "usage": self.usage,
            "over_budget": self.over_budget,
        }


# Куда ходить, если базовый URL не задан явно
DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
}


class LLMService:
    """Unified LLM service with provider abstraction."""

    def __init__(
        self,
        provider: str = None,
        model: str = None,
        api_key: str = None,
        base_url: str = None,
        system_prompt: str = "",
    ):
        self.provider = provider or LLM_PROVIDER
        self.model = model or LLM_MODEL
        self.api_key = api_key or LLM_API_KEY
        self.base_url = base_url or DEFAULT_BASE_URLS.get(self.provider) or LLM_BASE_URL
        self.system_prompt = system_prompt
        
        # Gemini specific config
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        
        logger.info(f"LLM Service initialized: {self.provider}/{self.model}")
    
    async def chat(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stream: bool = False,
        kind: str = budget.INTERACTIVE,
    ) -> LLMResponse:
        """Send chat completion request.

        `kind` решает судьбу вызова при исчерпанном дневном бюджете (I-4):
        фоновый отклоняется, интерактивный проходит с пометкой.
        """
        within_budget = budget.check(kind)

        if self.provider == "ollama":
            response = await self._ollama_chat(messages, temperature, max_tokens)
        elif self.provider == "gemini":
            response = await self._gemini_chat(messages, temperature, max_tokens)
        elif self.provider in ("openai", "anthropic", "deepseek"):
            response = await self._openai_compat_chat(messages, temperature, max_tokens)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        cost = budget.record(response.model, response.usage)
        if cost:
            response.usage["cost_usd"] = round(cost, 6)
        response.over_budget = not within_budget
        return response
    
    async def generate_plan(self, audio_path: str, prompt: str) -> str:
        """Generate plan from audio using Gemini 2.0 Flash."""
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not set for audio processing")
        
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        
        # Read audio file and encode as base64
        import base64
        with open(audio_path, "rb") as f:
            audio_data = base64.b64encode(f.read()).decode("utf-8")
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "audio/mpeg",
                            "data": audio_data
                        }
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 2048,
            }
        }
        
        headers = {
            "Content-Type": "application/json",
        }
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    f"{url}?key={self.gemini_api_key}",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return content
            except Exception as e:
                logger.error(f"Gemini audio processing failed: {e}")
                raise
    
    async def generate_response(
        self,
        user_message: str,
        context: str = "",
        kind: str = budget.INTERACTIVE,
    ) -> str:
        """Generate response for chat using configured LLM."""
        full_prompt = f"Context: {context}\n\nUser: {user_message}\n\nAssistant:"
        messages = []
        if self.system_prompt:
            messages.append(LLMMessage(role="system", content=self.system_prompt))
        messages.append(LLMMessage(role="user", content=full_prompt))

        response = await self.chat(messages, temperature=0.7, max_tokens=512, kind=kind)
        return response.content
    
    async def _ollama_chat(
        self,
        messages: List[LLMMessage],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Chat with Ollama."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                content = data.get("message", {}).get("content", "")
                usage = {
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                }
                
                return LLMResponse(content=content, model=self.model, usage=usage)
            except Exception as e:
                logger.error(f"Ollama chat failed: {e}")
                raise
    
    async def _gemini_chat(
        self,
        messages: List[LLMMessage],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Chat with Google Gemini."""
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not set")
        
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        
        # Convert messages to Gemini format
        gemini_parts = []
        for msg in messages:
            if msg.role == "system":
                gemini_parts.append({"text": f"[System instruction]: {msg.content}"})
            elif msg.role == "user":
                gemini_parts.append({"text": msg.content})
            elif msg.role == "assistant":
                gemini_parts.append({"text": msg.content})
        
        payload = {
            "contents": [{"parts": gemini_parts}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }
        
        headers = {"Content-Type": "application/json"}
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{url}?key={self.gemini_api_key}",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                usage = {}  # Gemini doesn't provide token counts in simple API
                
                return LLMResponse(content=content, model="gemini-2.0-flash", usage=usage)
            except Exception as e:
                logger.error(f"Gemini chat failed: {e}")
                raise
    
    async def _openai_compat_chat(
        self,
        messages: List[LLMMessage],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Chat with OpenAI-compatible API."""
        if self.provider == "anthropic":
            # Anthropic uses different endpoint
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            
            # Convert to Anthropic format
            system_msg = ""
            chat_messages = []
            for m in messages:
                if m.role == "system":
                    system_msg = m.content
                else:
                    chat_messages.append(m.to_dict())
            
            payload = {
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system_msg,
                "messages": chat_messages,
            }
        else:
            # OpenAI format
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": [m.to_dict() for m in messages],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                
                if self.provider == "anthropic":
                    content = data.get("content", [{}])[0].get("text", "")
                    usage = data.get("usage", {})
                else:
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    usage = data.get("usage", {})
                
                return LLMResponse(content=content, model=self.model, usage=usage)
            except Exception as e:
                logger.error(f"OpenAI-compatible chat failed: {e}")
                raise
    
    async def embed(self, text: str) -> List[float]:
        """Generate embeddings (if supported by provider)."""
        if self.provider == "ollama":
            return await self._ollama_embed(text)
        else:
            raise NotImplementedError(f"Embeddings not implemented for {self.provider}")
    
    async def _ollama_embed(self, text: str) -> List[float]:
        """Generate embeddings with Ollama."""
        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": self.model,
            "prompt": text,
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("embedding", [])
            except Exception as e:
                logger.error(f"Ollama embeddings failed: {e}")
                raise


# Singleton instance
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get or create LLM service instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


# Convenience functions
async def chat(
    messages: List[LLMMessage],
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> LLMResponse:
    """Quick chat function."""
    service = get_llm_service()
    return await service.chat(messages, temperature, max_tokens)


async def embed(text: str) -> List[float]:
    """Quick embedding function."""
    service = get_llm_service()
    return await service.embed(text)
