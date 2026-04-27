"""Tests for Unicode normalization (soft hyphens, ligatures, control chars)."""

from pdf2md.enhancers.unicode_normalizer import normalize_unicode_text


def test_soft_hyphen_between_letters_becomes_real_hyphen():
    assert normalize_unicode_text("micro\xadbiota") == "micro-biota"
    # \x02 is the soft-hyphen variant emitted by some PostScript fonts.
    assert normalize_unicode_text("micro\x02biota") == "micro-biota"


def test_soft_hyphen_at_end_of_line_is_stripped():
    assert normalize_unicode_text("end-of-line\xad\n") == "end-of-line\n"
    assert normalize_unicode_text("end-of-line\x02\n") == "end-of-line\n"


def test_soft_hyphen_before_punctuation_is_stripped():
    assert normalize_unicode_text("trailing\xad.") == "trailing."


def test_ligatures_expand():
    assert normalize_unicode_text("oﬀice") == "office"
    assert normalize_unicode_text("efﬁcient") == "efficient"
    assert normalize_unicode_text("ﬂow") == "flow"
    assert normalize_unicode_text("aﬃliation") == "affiliation"
    assert normalize_unicode_text("baﬄes") == "baffles"
    assert normalize_unicode_text("soﬅ") == "soft"
    assert normalize_unicode_text("beﬆ") == "best"


def test_control_characters_stripped():
    assert normalize_unicode_text("hello\x07world") == "helloworld"
    assert normalize_unicode_text("esc\x1bape") == "escape"
    assert normalize_unicode_text("\x00null\x1f") == "null"


def test_tabs_and_newlines_preserved():
    assert normalize_unicode_text("col1\tcol2\nrow2") == "col1\tcol2\nrow2"
    assert normalize_unicode_text("line\r\nbreak") == "line\r\nbreak"


def test_idempotent():
    text = "micro\xadbiota ﬁnal\x07 end-of-line\x02\n"
    once = normalize_unicode_text(text)
    twice = normalize_unicode_text(once)
    assert once == twice


def test_empty_string():
    assert normalize_unicode_text("") == ""


def test_plain_text_unchanged():
    text = "Plain ASCII text with no funny characters."
    assert normalize_unicode_text(text) == text


def test_nature_title_integration():
    """The motivating example from the Nature paper title."""
    raw = "Spatially restricted immune and microbiota\x02driven adaptation of the gut"
    expected = "Spatially restricted immune and microbiota-driven adaptation of the gut"
    assert normalize_unicode_text(raw) == expected
