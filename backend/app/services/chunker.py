"""Document chunking engine with paragraph/sentence boundary splitting and token overlap."""
import re
from dataclasses import dataclass
from typing import List, Optional

import tiktoken

from app.services.extractor import ExtractedPage


@dataclass
class ProcessedChunk:
    """A semantic document chunk ready for embedding and indexing."""
    content: str
    chunk_index: int
    page_number: Optional[int]
    token_count: int


class Chunker:
    """Splits document text into overlapping chunks respecting natural semantic boundaries."""

    def __init__(
        self,
        target_chunk_size: int = 600,
        overlap_tokens: int = 90,  # ~15% overlap
        encoding_name: str = "cl100k_base",
    ) -> None:
        self.target_chunk_size = target_chunk_size
        self.overlap_tokens = overlap_tokens
        try:
            self.tokenizer = tiktoken.get_encoding(encoding_name)
        except Exception:
            self.tokenizer = None

    def count_tokens(self, text: str) -> int:
        """Count tokens in text, falling back to word estimation if tokenizer fails."""
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        return int(len(text.split()) * 1.33)

    def _split_into_units(self, text: str) -> List[str]:
        """Split text into paragraphs, and oversized paragraphs into sentences."""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        units: List[str] = []

        for p in paragraphs:
            # If paragraph itself is under target size, keep it whole
            if self.count_tokens(p) <= self.target_chunk_size:
                units.append(p)
            else:
                # Split large paragraphs on sentence boundaries
                sentences = [
                    s.strip()
                    for s in re.split(r"(?<=[.!?])\s+", p)
                    if s.strip()
                ]
                units.extend(sentences)

        return units

    def chunk_pages(self, pages: List[ExtractedPage]) -> List[ProcessedChunk]:
        """Chunk a list of extracted pages into indexable chunks with overlap."""
        if not pages:
            return []

        chunks: List[ProcessedChunk] = []
        global_chunk_index = 0

        for page in pages:
            text = page.content.strip()
            if not text:
                continue

            units = self._split_into_units(text)
            if not units:
                continue

            current_units: List[str] = []
            current_tokens = 0

            for unit in units:
                unit_tokens = self.count_tokens(unit)

                if current_tokens + unit_tokens > self.target_chunk_size and current_units:
                    chunk_text = "\n\n".join(current_units)
                    chunks.append(
                        ProcessedChunk(
                            content=chunk_text,
                            chunk_index=global_chunk_index,
                            page_number=page.page_number,
                            token_count=current_tokens,
                        )
                    )
                    global_chunk_index += 1

                    # Compute overlap: take trailing units until ~overlap_tokens reached
                    overlap_units: List[str] = []
                    overlap_tok_count = 0
                    for u in reversed(current_units):
                        toks = self.count_tokens(u)
                        if overlap_tok_count + toks <= self.overlap_tokens:
                            overlap_units.insert(0, u)
                            overlap_tok_count += toks
                        else:
                            break

                    current_units = overlap_units.copy()
                    current_tokens = overlap_tok_count

                current_units.append(unit)
                current_tokens += unit_tokens

            # Flush remaining accumulated units
            if current_units:
                chunk_text = "\n\n".join(current_units)
                chunks.append(
                    ProcessedChunk(
                        content=chunk_text,
                        chunk_index=global_chunk_index,
                        page_number=page.page_number,
                        token_count=current_tokens,
                    )
                )
                global_chunk_index += 1

        return chunks
