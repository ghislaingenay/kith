"""Direct unit tests for the page text cleaner (#48, ADR-0011)."""

from documents.text_cleaner import CLEANER_VERSION, clean_text


def test_a_hyphenated_line_break_is_rejoined() -> None:
    assert clean_text("The docu-\nment is long") == "The document is long"


def test_a_hyphenated_break_with_windows_line_endings_is_rejoined() -> None:
    assert clean_text("The docu-\r\nment") == "The document"


def test_a_hyphen_before_a_capital_is_kept() -> None:
    assert clean_text("Jean-\nPaul") == "Jean-Paul"


def test_a_hyphen_inside_a_line_is_untouched() -> None:
    assert clean_text("well-known fact") == "well-known fact"


def test_a_soft_line_break_inside_a_paragraph_becomes_a_space() -> None:
    assert clean_text("first line\nsecond line") == "first line second line"


def test_real_paragraph_breaks_are_kept() -> None:
    assert clean_text("one\ntwo\n\nthree\n\n\n\nfour") == "one two\n\nthree\n\nfour"


def test_a_blank_line_holding_only_spaces_is_still_a_paragraph_break() -> None:
    assert clean_text("one\n  \t \ntwo") == "one\n\ntwo"


def test_nfkc_normalises_ligatures_and_special_spaces() -> None:
    assert clean_text("o\ufb03ce\u00a0\u2460") == "office 1"


def test_control_and_zero_width_characters_are_removed() -> None:
    assert clean_text("a\x00b\x07c\u200bd\u200ce\ufeff\u00adf") == "abcdef"


def test_runs_of_whitespace_collapse_and_edges_are_trimmed() -> None:
    assert clean_text("  a \t  b  \n  c  ") == "a b c"


def test_case_accents_and_wording_are_untouched() -> None:
    text = "Élève À L'École, Ça va ÉTÉ"
    assert clean_text(text) == text


def test_french_hyphenated_break_is_rejoined_with_accents_kept() -> None:
    assert clean_text("une for-\nmation générale\nexcellente") == (
        "une formation générale excellente"
    )


def test_empty_and_whitespace_only_text_cleans_to_empty() -> None:
    assert clean_text("") == ""
    assert clean_text(" \n\t\n ") == ""


def test_the_cleaner_has_a_version() -> None:
    assert isinstance(CLEANER_VERSION, int)
    assert CLEANER_VERSION >= 1


def test_form_feed_vertical_tab_and_next_line_separate_words_like_line_breaks() -> None:
    assert clean_text("ab\x0cc\x0bd\x85e") == "ab c d e"
