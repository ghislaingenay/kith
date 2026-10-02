"""Cuts one page's Clean Text into Chunks (ADR-0011).

Sizes are measured in tokens of a general tokenizer (`cl100k_base`) through
LangChain's recursive splitter, which prefers paragraph breaks, then
sentence ends, then spaces, then single characters. The splitter's own
start indexes are not trusted: offsets are found and verified here, and a
Chunk whose slice of the Clean Text does not match its text keeps unknown
offsets and a logged warning."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import tiktoken
from core.logging import setup_logger
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = setup_logger(__name__)

CHUNK_TOKENIZER = "cl100k_base"

# Paragraph break (the only newline Clean Text keeps), sentence end followed
# by a space, space, then single characters.
_SEPARATORS = ["\n\n", r"(?<=[.?!]) ", " ", ""]


@dataclass(frozen=True)
class ChunkDraft:
    text: str
    char_start: int | None
    char_end: int | None
    token_count: int


class _TextSplitter(Protocol):
    def split_text(self, text: str) -> list[str]: ...


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(CHUNK_TOKENIZER)


def _count_tokens(text: str) -> int:
    return len(_encoding().encode(text, disallowed_special=()))


def _splitter(size: int, overlap: int) -> _TextSplitter:
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=CHUNK_TOKENIZER,
        chunk_size=size,
        chunk_overlap=overlap,
        separators=_SEPARATORS,
        is_separator_regex=True,
        keep_separator="end",
        disallowed_special=(),
    )


def chunk_page(clean_text: str, *, size: int, overlap: int) -> list[ChunkDraft]:
    if not clean_text.strip():
        return []
    drafts: list[ChunkDraft] = []
    search_from = 0
    for text in _splitter(size, overlap).split_text(clean_text):
        start = clean_text.find(text, search_from)
        if start == -1 or clean_text[start : start + len(text)] != text:
            logger.warning(
                "chunk_offsets_mismatch",
                chunk_ordinal_on_page=len(drafts),
                chunk_length=len(text),
            )
            drafts.append(ChunkDraft(text, None, None, _count_tokens(text)))
            continue
        drafts.append(ChunkDraft(text, start, start + len(text), _count_tokens(text)))
        # The next Chunk can start inside this one (overlap) but never before
        # this one's own start.
        search_from = start + 1
    return drafts
