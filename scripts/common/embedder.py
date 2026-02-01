"""
ECHO OS Barebone: Embedding Utilities

Generate embeddings using OpenAI's embedding API.
"""

import os
import time
from typing import List, Optional
import numpy as np

from openai import OpenAI


class EmbeddingService:
    """OpenAI embedding service."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        batch_size: int = 100,
        retry_count: int = 3,
        retry_delay: float = 1.0
    ):
        """Initialize embedding service.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Embedding model name
            dimension: Embedding dimension
            batch_size: Batch size for API calls
            retry_count: Number of retries on failure
            retry_delay: Delay between retries in seconds
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable.")

        self.client = OpenAI(api_key=self.api_key)
        self.model = model
        self.dimension = dimension
        self.batch_size = batch_size
        self.retry_count = retry_count
        self.retry_delay = retry_delay

    def embed(self, text: str) -> np.ndarray:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding as numpy array
        """
        embeddings = self.embed_batch([text])
        return embeddings[0]

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings as numpy arrays
        """
        if not texts:
            return []

        all_embeddings = []

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]

            # Clean texts
            batch = [self._clean_text(t) for t in batch]

            for attempt in range(self.retry_count):
                try:
                    response = self.client.embeddings.create(
                        input=batch,
                        model=self.model
                    )

                    batch_embeddings = [
                        np.array(item.embedding, dtype=np.float32)
                        for item in response.data
                    ]
                    all_embeddings.extend(batch_embeddings)
                    break

                except Exception as e:
                    if attempt < self.retry_count - 1:
                        time.sleep(self.retry_delay * (attempt + 1))
                    else:
                        raise RuntimeError(f"Embedding failed after {self.retry_count} retries: {e}")

        return all_embeddings

    def _clean_text(self, text: str) -> str:
        """Clean text for embedding.

        Args:
            text: Raw text

        Returns:
            Cleaned text
        """
        if not text:
            return " "  # OpenAI API requires non-empty string

        # Replace newlines with spaces
        text = text.replace("\n", " ")

        # Remove excessive whitespace
        text = " ".join(text.split())

        # Truncate if too long (model has token limit)
        # Rough estimate: 1 token ≈ 4 characters for English, 1.5 for Japanese
        max_chars = 8000 * 2  # Conservative limit
        if len(text) > max_chars:
            text = text[:max_chars]

        return text if text else " "


# Global instance
_embedder: Optional[EmbeddingService] = None


def get_embedder() -> EmbeddingService:
    """Get global embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingService()
    return _embedder


def embed_text(text: str) -> np.ndarray:
    """Generate embedding for text.

    Args:
        text: Text to embed

    Returns:
        Embedding as numpy array
    """
    return get_embedder().embed(text)


def embed_texts(texts: List[str]) -> List[np.ndarray]:
    """Generate embeddings for multiple texts.

    Args:
        texts: List of texts to embed

    Returns:
        List of embeddings as numpy arrays
    """
    return get_embedder().embed_batch(texts)
