"""Tests for pypdfium2 extractor."""

from io import BytesIO
from unittest.mock import patch

import pypdfium2 as pdfium
import pytest
from pdfvault.extractors.base import PageContent
from pdfvault.extractors.pypdfium_ext import (
    PypdfiumExtractor,
    _is_two_column_layout,
)


def _build_two_column_pdf() -> bytes:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    page_w, page_h = letter
    top_y = page_h - 60.0
    for i in range(25):
        y = top_y - i * 18.0
        c.drawString(50.0, y, f"LEFT-{i:02d} left content here paragraph more text")
        c.drawString(page_w / 2 + 30.0, y, f"RIGHT-{i:02d} right content paragraph more text")
    c.save()
    return buf.getvalue()


def _build_single_column_pdf() -> bytes:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    _, page_h = letter
    top_y = page_h - 60.0
    for i in range(25):
        y = top_y - i * 18.0
        c.drawString(60.0, y, f"LINE-{i:02d} a single column line of body text content")
    c.save()
    return buf.getvalue()


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


def test_is_two_column_layout_detects_two_columns():
    pdf = pdfium.PdfDocument(_build_two_column_pdf())
    page = pdf[0]
    width, _ = page.get_size()
    tp = page.get_textpage()
    try:
        assert _is_two_column_layout(tp, width) is True
    finally:
        tp.close()
        page.close()
        pdf.close()


def test_is_two_column_layout_rejects_single_column():
    pdf = pdfium.PdfDocument(_build_single_column_pdf())
    page = pdf[0]
    width, _ = page.get_size()
    tp = page.get_textpage()
    try:
        assert _is_two_column_layout(tp, width) is False
    finally:
        tp.close()
        page.close()
        pdf.close()


def test_pypdfium_falls_back_to_pdfplumber_for_2_column():
    """When 2-column layout is detected the pypdfium extractor must
    delegate to pdfplumber so reading order is preserved."""
    pdf_bytes = _build_two_column_pdf()
    sentinel = "FALLBACK-PDFPLUMBER-TEXT-MARKER"
    fake_page = PageContent(
        page_number=0,
        text=sentinel,
        tables=[],
        figures=[],
        confidence=0.9,
    )

    with patch(
        "pdfvault.extractors.pdfplumber_ext.PdfplumberExtractor.extract_page",
        return_value=fake_page,
    ) as spy:
        page = PypdfiumExtractor().extract_page(pdf_bytes, 0)

    assert spy.called, "pdfplumber fallback was not invoked for 2-column PDF"
    assert sentinel in page.text


def test_pypdfium_skips_fallback_for_single_column():
    """Single-column pages must keep the fast pdfium path (no pdfplumber call)."""
    pdf_bytes = _build_single_column_pdf()
    with patch(
        "pdfvault.extractors.pdfplumber_ext.PdfplumberExtractor.extract_page",
    ) as spy:
        page = PypdfiumExtractor().extract_page(pdf_bytes, 0)

    assert not spy.called, "pdfplumber fallback should not run on single-column pages"
    assert "LINE-00" in page.text
