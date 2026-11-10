"""Abstract embedding provider interface and implementations (Gemini, Sentence-Transformers, Mock)."""
import asyncio
import hashlib
import logging
import math
from abc import ABC, abstractmethod
from typing import List

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """Abstract interface for embedding generation."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimensionality."""
        pass

    @abstractmethod
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of document chunks with batching."""
        pass

    @abstractmethod
    async def embed_query(self, query: str) -> List[float]:
        """Generate embedding vector for a single query."""
        pass


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic mock embedding provider for tests and offline development."""

    def __init__(self, dimension: int = settings.EMBEDDING_DIMENSION) -> None:
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def _generate_vector(self, text: str) -> List[float]:
        # Generate pseudo-random deterministic normalized vector from text hash
        raw_hash = hashlib.sha256(text.encode("utf-8")).digest()
        vector = []
        for i in range(self._dim):
            byte_val = raw_hash[i % len(raw_hash)]
            vector.append(float((byte_val + i) % 256) / 256.0 - 0.5)

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self._generate_vector(t) for t in texts]

    async def embed_query(self, query: str) -> List[float]:
        return self._generate_vector(query)


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini embedding provider with retry and batching."""

    def __init__(
        self,
        api_key: str = settings.GEMINI_API_KEY,
        model: str = "text-embedding-004",
        dimension: int = 768,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self._dim = dimension
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    @property
    def dimension(self) -> int:
        return self._dim

    async def _embed_batch_with_retry(
        self, texts: List[str], max_retries: int = 3
    ) -> List[List[float]]:
        """Call Gemini batchEmbedContents with exponential backoff."""
        url = f"{self.base_url}/models/{self.model}:batchEmbedContents?key={self.api_key}"
        requests_payload = [
            {"model": f"models/{self.model}", "content": {"parts": [{"text": t}]}}
            for t in texts
        ]

        delay = 1.0
        last_error = None

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, json={"requests": requests_payload})
                    if response.status_code == 200:
                        data = response.json()
                        return [
                            item["values"]
                            for item in data.get("embeddings", [])
                        ]
                    response.raise_for_status()
            except Exception as e:
                last_error = e
                logger.warning(
                    "Gemini embedding attempt %d failed: %s. Retrying in %.1fs...",
                    attempt + 1,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
                delay *= 2.0

        raise RuntimeError(f"Gemini embedding failed after {max_retries} retries: {last_error}")

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        batch_size = 50
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = await self._embed_batch_with_retry(batch)
            all_embeddings.extend(embeddings)
        return all_embeddings

    async def embed_query(self, query: str) -> List[float]:
        results = await self.embed_texts([query])
        return results[0]


class SentenceTransformersEmbeddingProvider(EmbeddingProvider):
    """Sentence-Transformers provider (local CPU/GPU embeddings)."""

    def __init__(
        self,
        model_name: str = settings.EMBEDDING_MODEL,
        dimension: int = settings.EMBEDDING_DIMENSION,
    ) -> None:
        self.model_name = model_name
        self._dim = dimension
        self._model = None

    @property
    def dimension(self) -> int:
        return self._dim

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except ImportError as exc:
                logger.warning(
                    "sentence-transformers not installed, falling back to mock: %s",
                    exc,
                )
                return None
        return self._model

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        if model is None:
            mock = MockEmbeddingProvider(dimension=self._dim)
            return await mock.embed_texts(texts)

        # Run encoding in worker thread to prevent blocking event loop
        embeddings = await asyncio.to_thread(
            model.encode, texts, normalize_embeddings=True
        )
        return [e.tolist() for e in embeddings]

    async def embed_query(self, query: str) -> List[float]:
        results = await self.embed_texts([query])
        return results[0]


def get_embedding_provider() -> EmbeddingProvider:
    """Dependency provider returning the configured embedding provider."""
    provider_name = settings.EMBEDDING_PROVIDER.lower().strip()
    if provider_name == "gemini" and settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "mock_key":
        return GeminiEmbeddingProvider()
    elif provider_name == "sentence-transformers":
        return SentenceTransformersEmbeddingProvider()
    return MockEmbeddingProvider()
