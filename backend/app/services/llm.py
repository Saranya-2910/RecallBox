"""LLM Provider abstraction and implementations (Gemini, Mock) with retry and timeout."""
import asyncio
import logging
import re
from abc import ABC, abstractmethod
from typing import Callable, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract interface for large language model completions."""

    @abstractmethod
    async def generate_response(
        self, prompt: str, system_instruction: Optional[str] = None
    ) -> str:
        """Generate text completion from prompt and optional system instructions."""
        pass


class MockLLMProvider(LLMProvider):
    """Deterministic mock LLM provider for tests and offline development."""

    def __init__(
        self,
        custom_responder: Optional[Callable[[str, Optional[str]], str]] = None,
    ) -> None:
        self.custom_responder = custom_responder

    async def generate_response(
        self, prompt: str, system_instruction: Optional[str] = None
    ) -> str:
        if self.custom_responder:
            return self.custom_responder(prompt, system_instruction)

        # Check if context contains chunks
        chunk_matches = re.findall(r"\[Chunk\s+(\d+)\]", prompt)

        # If question is explicitly unanswerable or context has no chunks
        if not chunk_matches or "QuantumSuperpositionGraviton" in prompt or "NOT_FOUND_TRIGGER" in prompt:
            return "This information is not found in your saved material."

        # Grounded answer citing the first available chunk
        cited_id = chunk_matches[0]
        return (
            f"Based on your saved material [Chunk {cited_id}], "
            f"the system provides the requested technical capability."
        )


class GeminiLLMProvider(LLMProvider):
    """Google Gemini LLM provider with timeout and exponential backoff retry."""

    def __init__(
        self,
        api_key: str = settings.GEMINI_API_KEY,
        model: str = settings.GEMINI_MODEL,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    async def generate_response(
        self, prompt: str, system_instruction: Optional[str] = None
    ) -> str:
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"

        contents = [{"parts": [{"text": prompt}]}]
        payload = {"contents": contents}

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        delay = 1.0
        last_error = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        candidates = data.get("candidates", [])
                        if candidates and "content" in candidates[0]:
                            parts = candidates[0]["content"].get("parts", [])
                            if parts and "text" in parts[0]:
                                return parts[0]["text"]
                        return "This information is not found in your saved material."
                    response.raise_for_status()
            except Exception as e:
                last_error = e
                logger.warning(
                    "Gemini completion attempt %d failed: %s. Retrying in %.1fs...",
                    attempt + 1,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
                delay *= 2.0

        raise RuntimeError(f"Gemini LLM call failed after {self.max_retries} attempts: {last_error}")


def get_llm_provider() -> LLMProvider:
    """Dependency provider returning the active LLM backend."""
    provider_name = settings.LLM_PROVIDER.lower().strip()
    if provider_name == "gemini" and settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "mock_key":
        return GeminiLLMProvider()
    return MockLLMProvider()
