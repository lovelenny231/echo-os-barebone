"""
ECHO OS Barebone: Text Chunking Utilities

Chunking strategies for RAG document processing.
"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class Chunk:
    """A text chunk with metadata."""
    content: str
    chunk_id: str
    source: str
    metadata: Dict[str, Any]


class SemanticChunker:
    """Semantic text chunker.

    Splits text into chunks based on semantic boundaries (paragraphs, sections)
    while respecting max_tokens limit.
    """

    def __init__(
        self,
        max_tokens: int = 500,
        overlap_tokens: int = 50,
        separator_patterns: Optional[List[str]] = None
    ):
        """Initialize chunker.

        Args:
            max_tokens: Maximum tokens per chunk
            overlap_tokens: Token overlap between chunks
            separator_patterns: Regex patterns for semantic boundaries
        """
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.separator_patterns = separator_patterns or [
            r'\n\n+',           # Multiple newlines (paragraph)
            r'\n第[一二三四五六七八九十百千]+条',  # Japanese article numbers
            r'\n第\d+条',       # Numbered articles
            r'\n[第（\(]\d+[）\)]',  # Numbered sections
            r'\n#{1,3}\s',      # Markdown headers
            r'\n',              # Single newline (fallback)
        ]

    def chunk(self, text: str, source: str = "", base_metadata: Optional[Dict] = None) -> List[Chunk]:
        """Split text into semantic chunks.

        Args:
            text: Text to chunk
            source: Source identifier
            base_metadata: Base metadata for all chunks

        Returns:
            List of Chunk objects
        """
        if not text or not text.strip():
            return []

        base_metadata = base_metadata or {}
        chunks = []

        # Try each separator pattern
        segments = [text]
        for pattern in self.separator_patterns:
            new_segments = []
            for segment in segments:
                if self._estimate_tokens(segment) > self.max_tokens:
                    split = re.split(pattern, segment)
                    new_segments.extend([s for s in split if s.strip()])
                else:
                    new_segments.append(segment)
            segments = new_segments

        # Merge small segments and create chunks
        current_text = ""
        chunk_index = 0

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue

            combined = f"{current_text}\n\n{segment}" if current_text else segment
            combined_tokens = self._estimate_tokens(combined)

            if combined_tokens <= self.max_tokens:
                current_text = combined
            else:
                # Save current chunk
                if current_text:
                    chunks.append(Chunk(
                        content=current_text,
                        chunk_id=f"{source}_{chunk_index}",
                        source=source,
                        metadata={
                            **base_metadata,
                            "chunk_index": chunk_index,
                            "token_count": self._estimate_tokens(current_text),
                        }
                    ))
                    chunk_index += 1

                # Start new chunk (with overlap if previous existed)
                if current_text and self.overlap_tokens > 0:
                    overlap_text = self._get_overlap(current_text)
                    current_text = f"{overlap_text}\n\n{segment}" if overlap_text else segment
                else:
                    current_text = segment

                # Handle segment larger than max_tokens
                while self._estimate_tokens(current_text) > self.max_tokens:
                    # Force split at max_tokens
                    split_point = self._find_split_point(current_text)
                    chunks.append(Chunk(
                        content=current_text[:split_point],
                        chunk_id=f"{source}_{chunk_index}",
                        source=source,
                        metadata={
                            **base_metadata,
                            "chunk_index": chunk_index,
                            "token_count": self._estimate_tokens(current_text[:split_point]),
                            "force_split": True,
                        }
                    ))
                    chunk_index += 1
                    current_text = current_text[split_point:].strip()

        # Add final chunk
        if current_text:
            chunks.append(Chunk(
                content=current_text,
                chunk_id=f"{source}_{chunk_index}",
                source=source,
                metadata={
                    **base_metadata,
                    "chunk_index": chunk_index,
                    "token_count": self._estimate_tokens(current_text),
                }
            ))

        return chunks

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count.

        Simple estimation: ~1.5 characters per token for Japanese,
        ~4 characters per token for English.
        """
        if not text:
            return 0

        # Count Japanese characters
        japanese_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', text))
        other_chars = len(text) - japanese_chars

        return int(japanese_chars / 1.5) + int(other_chars / 4)

    def _get_overlap(self, text: str) -> str:
        """Get overlap text from end of chunk."""
        tokens_needed = self.overlap_tokens
        # Estimate characters needed
        chars_needed = int(tokens_needed * 2)  # Conservative estimate

        if len(text) <= chars_needed:
            return text

        overlap = text[-chars_needed:]

        # Try to start at sentence boundary
        sentence_start = overlap.find('。')
        if sentence_start > 0 and sentence_start < len(overlap) - 10:
            overlap = overlap[sentence_start + 1:]

        return overlap.strip()

    def _find_split_point(self, text: str) -> int:
        """Find best split point near max_tokens."""
        # Estimate characters at max_tokens
        target_chars = int(self.max_tokens * 2)

        if len(text) <= target_chars:
            return len(text)

        # Look for sentence boundary near target
        search_start = max(0, target_chars - 100)
        search_end = min(len(text), target_chars + 100)
        search_region = text[search_start:search_end]

        # Try to split at sentence end
        for marker in ['。', '.\n', '\n\n', '\n']:
            pos = search_region.rfind(marker)
            if pos > 0:
                return search_start + pos + len(marker)

        return target_chars


def chunk_text(
    text: str,
    max_tokens: int = 500,
    overlap_tokens: int = 50,
    source: str = "",
    metadata: Optional[Dict] = None
) -> List[Chunk]:
    """Convenience function for text chunking.

    Args:
        text: Text to chunk
        max_tokens: Maximum tokens per chunk
        overlap_tokens: Token overlap between chunks
        source: Source identifier
        metadata: Base metadata

    Returns:
        List of Chunk objects
    """
    chunker = SemanticChunker(
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens
    )
    return chunker.chunk(text, source, metadata)
