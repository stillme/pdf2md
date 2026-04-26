"""Tests for pdfplumber table extractor."""

import pytest
from pdf2md.extractors.pdfplumber_ext import PdfplumberExtractor, _table_confidence


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


def test_table_confidence_clean_table():
    headers = ["Condition", "Mean", "SD", "p-value"]
    rows = [
        ["Control", "12.3", "2.1", "-"],
        ["Treatment A", "18.7", "3.4", "0.002"],
        ["Treatment B", "15.1", "2.8", "0.041"],
        ["Treatment C", "16.0", "3.0", "0.030"],
        ["Treatment D", "17.2", "2.9", "0.020"],
    ]
    assert _table_confidence(headers, rows) >= 0.8


def test_table_confidence_high_padding():
    headers = ["A", "B", "C", "D", "E"]
    # 5 cols x 5 rows = 25 row cells, plus 5 header cells = 30 total.
    # 18 empty out of 30 = 60% padding.
    rows = [
        ["x", "", "", "", ""],
        ["", "y", "", "", ""],
        ["", "", "z", "", ""],
        ["", "", "", "w", ""],
        ["", "", "", "", "v"],
    ]
    assert _table_confidence(headers, rows) < 0.7


def test_table_confidence_ragged_columns():
    headers = ["A", "B", "C", "D"]
    rows = [
        ["1", "2", "3", "4"],
        ["1", "2"],
        ["1", "2", "3"],
        ["1"],
    ]
    assert _table_confidence(headers, rows) < 0.7


def test_table_confidence_one_row():
    headers = ["A", "B", "C"]
    rows = [["1", "2", "3"]]
    assert _table_confidence(headers, rows) < 0.7


def test_table_confidence_numeric_header():
    # Header looks like data (all numeric) — likely a misparsed first row.
    headers = ["1.0", "2.5", "3.7", "4.2"]
    rows = [
        ["a", "b", "c", "d"],
        ["e", "f", "g", "h"],
        ["i", "j", "k", "l"],
    ]
    assert _table_confidence(headers, rows) < 0.8
