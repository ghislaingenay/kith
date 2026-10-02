"""Tests for `chunk_page` (#49): one page's Clean Text cut into Chunks whose
offsets we verify ourselves (ADR-0011)."""

from unittest.mock import patch

import pytest
from documents.chunker import chunk_page

_SENTENCE = "Le contrat prévoit une clause de résiliation anticipée. "


def _paragraphs(count: int, sentences: int = 12) -> str:
    return "\n\n".join(_SENTENCE * sentences for _ in range(count)).strip()


def test_blank_text_yields_no_chunks() -> None:
    assert chunk_page("", size=500, overlap=50) == []
    assert chunk_page("   \n\n ", size=500, overlap=50) == []


def test_short_page_is_one_chunk_covering_the_text() -> None:
    [chunk] = chunk_page("Hello world.", size=500, overlap=50)

    assert chunk.text == "Hello world."
    assert (chunk.char_start, chunk.char_end) == (0, 12)
    assert chunk.token_count == 3


def test_offsets_slice_clean_text_to_exactly_the_chunk_text() -> None:
    clean = _paragraphs(6)

    chunks = chunk_page(clean, size=100, overlap=10)

    assert len(chunks) > 3
    for chunk in chunks:
        assert chunk.char_start is not None and chunk.char_end is not None
        assert clean[chunk.char_start : chunk.char_end] == chunk.text


def test_chunks_stay_near_the_size_target() -> None:
    chunks = chunk_page(_paragraphs(10), size=100, overlap=10)

    assert all(chunk.token_count <= 100 for chunk in chunks)
    # Every Chunk but the last of the page is reasonably full.
    assert all(chunk.token_count >= 50 for chunk in chunks[:-1])


def test_consecutive_chunks_overlap() -> None:
    chunks = chunk_page(_paragraphs(6), size=100, overlap=20)

    assert any(
        later.char_start < earlier.char_end
        for earlier, later in zip(chunks, chunks[1:])
    )


def test_prefers_paragraph_boundaries() -> None:
    first = "Alpha beta gamma. " * 5
    second = "Delta epsilon zeta. " * 5
    clean = f"{first.strip()}\n\n{second.strip()}"

    chunks = chunk_page(clean, size=40, overlap=0)

    assert [chunk.text for chunk in chunks] == [first.strip(), second.strip()]


def test_cuts_oversized_paragraph_at_sentence_ends() -> None:
    clean = "One two three four. Five six seven eight. Nine ten eleven twelve."

    chunks = chunk_page(clean, size=12, overlap=0)

    assert all(chunk.text.endswith(".") for chunk in chunks)
    assert len(chunks) > 1


def test_a_single_unbreakable_word_is_still_cut() -> None:
    chunks = chunk_page("x" * 3000, size=50, overlap=0)

    assert len(chunks) > 1
    assert "".join(chunk.text for chunk in chunks) == "x" * 3000


def test_text_that_looks_like_a_special_token_does_not_raise() -> None:
    [chunk] = chunk_page("before <|endoftext|> after", size=500, overlap=50)

    assert chunk.text == "before <|endoftext|> after"


def test_mismatched_offsets_are_stored_unknown_and_warned(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _Splitter:
        def split_text(self, text: str) -> list[str]:
            return ["Hello world.", "not in the page"]

    with patch("documents.chunker._splitter", return_value=_Splitter()):
        chunks = chunk_page("Hello world.", size=500, overlap=50)

    assert (chunks[0].char_start, chunks[0].char_end) == (0, 12)
    assert (chunks[1].char_start, chunks[1].char_end) == (None, None)
    assert chunks[1].text == "not in the page"
    assert "chunk_offsets_mismatch" in capsys.readouterr().out
