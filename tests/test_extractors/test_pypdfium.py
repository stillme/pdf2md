"""Tests for pypdfium2 extractor."""

import pytest
from pdf2md.extractors.pypdfium_ext import PypdfiumExtractor


def test_extract_returns_pages(sample_pdf_bytes):
    ext = PypdfiumExtractor()
    result = ext.extract(sample_pdf_bytes)
    assert result.engine == "pypdfium2"
    assert len(result.pages) == 2


def test_extract_page_text(sample_pdf_bytes):
    ext = PypdfiumExtractor()
    page = ext.extract_page(sample_pdf_bytes, 0)
    assert page.page_number == 0
    assert "Introduction" in page.text
    assert "Sample Research Paper" in page.text
    assert page.confidence > 0.5


def test_extract_finds_table_region(sample_pdf_bytes):
    ext = PypdfiumExtractor()
    result = ext.extract(sample_pdf_bytes)
    page1_text = result.pages[0].text
    assert "Condition" in page1_text or "Control" in page1_text


def test_extract_page2_text(sample_pdf_bytes):
    ext = PypdfiumExtractor()
    page = ext.extract_page(sample_pdf_bytes, 1)
    assert "Discussion" in page.text
    assert "References" in page.text


def test_extract_confidence_based_on_text_density(sample_pdf_bytes):
    ext = PypdfiumExtractor()
    result = ext.extract(sample_pdf_bytes)
    for page in result.pages:
        assert page.confidence >= 0.7


def test_extract_empty_bytes():
    ext = PypdfiumExtractor()
    with pytest.raises(ValueError, match="Invalid PDF"):
        ext.extract(b"not a pdf")


def test_name_and_capabilities():
    ext = PypdfiumExtractor()
    assert ext.name == "pypdfium2"
    assert "text" in ext.capabilities
    assert "images" in ext.capabilities
