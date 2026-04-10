"""Tests for pdfplumber table extractor."""

import pytest
from pdf2md.extractors.pdfplumber_ext import PdfplumberExtractor


def test_extract_finds_table(sample_pdf_bytes):
    ext = PdfplumberExtractor()
    result = ext.extract(sample_pdf_bytes)
    assert result.engine == "pdfplumber"
    page1 = result.pages[0]
    assert len(page1.tables) >= 1


def test_table_has_headers(sample_pdf_bytes):
    ext = PdfplumberExtractor()
    result = ext.extract(sample_pdf_bytes)
    table = result.pages[0].tables[0]
    assert "Condition" in table.headers
    assert "Mean" in table.headers


def test_table_has_rows(sample_pdf_bytes):
    ext = PdfplumberExtractor()
    result = ext.extract(sample_pdf_bytes)
    table = result.pages[0].tables[0]
    assert len(table.rows) >= 3


def test_table_markdown_format(sample_pdf_bytes):
    ext = PdfplumberExtractor()
    result = ext.extract(sample_pdf_bytes)
    table = result.pages[0].tables[0]
    assert "|" in table.markdown
    assert "---" in table.markdown


def test_page_without_table(sample_pdf_bytes):
    ext = PdfplumberExtractor()
    result = ext.extract(sample_pdf_bytes)
    page2 = result.pages[1]
    assert len(page2.tables) == 0


def test_text_extraction(sample_pdf_bytes):
    ext = PdfplumberExtractor()
    result = ext.extract(sample_pdf_bytes)
    assert "Introduction" in result.pages[0].text


def test_invalid_pdf():
    ext = PdfplumberExtractor()
    with pytest.raises(ValueError, match="Invalid PDF"):
        ext.extract(b"not a pdf")
