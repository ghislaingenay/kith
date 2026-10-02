"""Turns a page's raw Page Text into its Clean Text (ADR-0011).

Never changes case, accents or wording, and does not remove headers,
footers or page numbers."""

import re
import unicodedata

CLEANER_VERSION = 1
"""Bumped by hand whenever the rules below change, so Documents cleaned by
an older version can be found and re-chunked."""

# Soft hyphen and the zero-width characters NFKC leaves in place.
_INVISIBLE = dict.fromkeys([0x00AD, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF])
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_HYPHENATED_BREAK = re.compile(r"(?<=\w)-[^\S\n]*\n[^\S\n]*(?=([^\W\d_]))")
_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")
_PARAGRAPH_BREAK = re.compile(r"\n(?:[ ]?\n)+")
_PARAGRAPH_MARK = "\x00"


def clean_text(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_INVISIBLE)
    text = _CONTROL.sub("", text)
    text = _HYPHENATED_BREAK.sub(_join_hyphenated, text)
    text = _HORIZONTAL_SPACE.sub(" ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = _PARAGRAPH_BREAK.sub(_PARAGRAPH_MARK, text)
    text = text.replace("\n", " ")
    return text.replace(_PARAGRAPH_MARK, "\n\n").strip()


def _join_hyphenated(match: re.Match[str]) -> str:
    """A word split across lines loses its hyphen; a hyphen before a capital
    ("Jean-\\nPaul") is a real one and stays."""
    return "" if match.group(1).islower() else "-"
