"""Tests for markdown quality fixes — soft hyphens, journal headers, false math."""

import pytest
from pdf2md.assembler import _clean_hyphens, _clean_page_text, _detect_repeated_lines
from pdf2md.enhancers.math import convert_unicode_math
from pdf2md.extractors.base import PageContent


# ── Soft hyphen removal ─────────────────────────────────────────────

class TestSoftHyphenRemoval:

    def test_replaces_uffbe_with_hyphen(self):
        """Inline U+FFBE should become a regular hyphen (compound word)."""
        text = "microbiota\uffbedriven adaptation"
        result = _clean_hyphens(text)
        assert "\uffbe" not in result
        assert "microbiota-driven" in result

    def test_replaces_ufffe_with_hyphen(self):
        """Inline U+FFFE should become a regular hyphen (compound word)."""
        text = "microbiota\ufffedriven adaptation"
        result = _clean_hyphens(text)
        assert "\ufffe" not in result
        assert "microbiota-driven" in result

    def test_removes_soft_hyphen_char(self):
        text = "micro\xadbiota"
        result = _clean_hyphens(text)
        assert "\xad" not in result
        assert "microbiota" in result

    def test_rejoins_uffbe_compound_across_lines(self):
        """Compound word at line break with U+FFBE keeps the hyphen."""
        text = "microbiota\uffbe\ndriven adaptation"
        result = _clean_hyphens(text)
        assert "microbiota-driven" in result

    def test_rejoins_ufffe_prefix_across_lines(self):
        """Combining prefix at line break with U+FFFE joins without hyphen."""
        text = "inte\ufffe\ngration of signals"
        result = _clean_hyphens(text)
        assert "integration" in result

    def test_rejoins_standard_hyphenated_break(self):
        text = "environ-\nmental pressures"
        result = _clean_hyphens(text)
        assert "environmental" in result

    def test_preserves_real_hyphens(self):
        """Hyphens NOT at line breaks should be preserved."""
        text = "well-known method"
        result = _clean_hyphens(text)
        assert "well-known" in result

    def test_no_change_on_clean_text(self):
        text = "Normal text without hyphens."
        result = _clean_hyphens(text)
        assert result == text


# ── Journal header stripping ────────────────────────────────────────

class TestJournalHeaders:

    def test_nature_header_stripped(self):
        text = "Nature | Vol 636 | 12 December 2024 | 447\nArticle\nReal content here."
        result = _clean_page_text(text, set())
        assert "Nature | Vol 636" not in result
        assert "Article" not in result
        assert "Real content" in result

    def test_nature_header_with_page_prefix(self):
        text = "448 | Nature | Vol 636 | 12 December 2024\nContent text."
        result = _clean_page_text(text, set())
        assert "Nature | Vol 636" not in result
        assert "Content text" in result

    def test_article_type_standalone(self):
        text = "Article\nReal content starts here."
        result = _clean_page_text(text, set())
        assert "Article" not in result
        assert "Real content" in result

    def test_non_header_nature_reference_preserved(self):
        """References to Nature in body text should NOT be stripped."""
        text = "First line of page content.\nSecond line here.\nThird line.\nPublished in Nature in 2024."
        result = _clean_page_text(text, set())
        assert "Published in Nature" in result

    def test_repeated_lines_in_positions_2_3(self):
        """Lines at position 2-3 that repeat across pages should be caught."""
        pages = []
        for i in range(6):
            pages.append(PageContent(
                page_number=i,
                text=f"{i+1}\nArticle\nSome unique content on page {i}.",
                tables=[], figures=[], confidence=0.9,
            ))
        repeated = _detect_repeated_lines(pages)
        assert "Article" in repeated


# ── False math wrapping ─────────────────────────────────────────────

class TestFalseMathWrapping:

    def test_plain_numbers_not_wrapped(self):
        """Lines with only numbers/spaces should NOT get $$ wrapping."""
        text = "-2 -1 0 1 2"
        result = convert_unicode_math(text)
        assert "$$" not in result

    def test_decimal_numbers_not_wrapped(self):
        text = "0.5 1.0 1.5 2.0"
        result = convert_unicode_math(text)
        assert "$$" not in result

    def test_negative_numbers_not_wrapped(self):
        text = "-0.5 0 0.5"
        result = convert_unicode_math(text)
        assert "$$" not in result

    def test_real_math_still_wrapped(self):
        """Lines with actual math symbols should still be wrapped."""
        text = "∇ · (κ∇u) = f"
        result = convert_unicode_math(text)
        assert "$$" in result or "$" in result
        assert r"\nabla" in result

    def test_greek_letters_still_converted(self):
        """Greek letters in sentences should still be handled."""
        text = "The parameters α and β satisfy α + β ≤ 1."
        result = convert_unicode_math(text)
        assert r"\alpha" in result
        assert r"\beta" in result

    def test_mixed_numbers_with_math_symbol(self):
        """Numbers combined with real math symbols should be wrapped."""
        text = "∑ᵢ xᵢ = 1"
        result = convert_unicode_math(text)
        assert "$" in result
