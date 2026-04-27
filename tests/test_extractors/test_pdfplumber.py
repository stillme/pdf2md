"""Tests for pdfplumber table extractor."""

from io import BytesIO
from unittest.mock import patch

import pytest
from pdf2md.extractors.pdfplumber_ext import (
    PdfplumberExtractor,
    _normalize_layout_whitespace,
    _table_confidence,
)


def _make_two_column_pdf() -> bytes:
    """Build a synthetic 2-column PDF with non-overlapping columns.

    Left column is taller than right (uneven heights) so the two columns
    cannot trivially be read row-by-row — column-aware extractors must
    walk top-to-bottom of column 1 then column 2.
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    page_w, page_h = letter
    left_x = 50.0
    right_x = page_w / 2 + 30.0
    top_y = page_h - 60.0
    # Short content so columns do not horizontally overlap.
    for i in range(20):
        y = top_y - i * 18.0
        c.drawString(left_x, y, f"LEFT-{i:02d} left col")
    # Right column has fewer entries so the bottom rows are left-only —
    # this guarantees columns must be read in column-major order.
    for i in range(8):
        y = top_y - i * 18.0
        c.drawString(right_x, y, f"RIGHT-{i:02d} right col")
    c.save()
    return buf.getvalue()


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


def test_pdfplumber_uses_layout_mode(sample_pdf_bytes):
    """The extractor must call extract_text(layout=True).

    Without layout=True pdfplumber ignores in-column line order. The
    column-aware path crops per-column and then calls extract_text with
    layout=True on each crop, so the spy still observes layout=True.
    """
    ext = PdfplumberExtractor()
    captured: dict = {}
    import pdfplumber.page as plumber_page
    real = plumber_page.Page.extract_text

    def spy(self, *args, **kwargs):
        # Record kwargs from the first text extraction call.
        captured.setdefault("kwargs", kwargs)
        return real(self, *args, **kwargs)

    with patch.object(plumber_page.Page, "extract_text", spy):
        ext.extract(sample_pdf_bytes)

    assert captured.get("kwargs", {}).get("layout") is True


def test_pdfplumber_two_column_separates_columns_completely():
    """Column-aware extraction returns the entire left column before any
    right-column text — not the row-by-row interleave that plain
    layout=True produces. Without this, ``faecal micro-`` from the end
    of column 1 lands on the same physical line as ``biota transplant``
    from the start of column 2 and the cleaner can't recover."""
    pdf_bytes = _make_two_column_pdf()
    ext = PdfplumberExtractor()
    page = ext.extract_page(pdf_bytes, 0)
    text = page.text

    # All left-col tokens present.
    assert "LEFT-00" in text and "LEFT-19" in text
    # All right-col tokens present.
    assert "RIGHT-00" in text and "RIGHT-07" in text

    # Strong invariant: every LEFT marker appears before every RIGHT
    # marker. This is what fails on Nature-style two-column papers
    # under plain layout=True.
    last_left = max(
        text.find(f"LEFT-{i:02d}") for i in range(20)
        if text.find(f"LEFT-{i:02d}") >= 0
    )
    first_right = min(
        text.find(f"RIGHT-{i:02d}") for i in range(8)
        if text.find(f"RIGHT-{i:02d}") >= 0
    )
    assert last_left < first_right, (
        f"Column order broken: last LEFT at {last_left}, "
        f"first RIGHT at {first_right} — RIGHT must come after all LEFT"
    )

    # Within each column, markers appear in numerical order.
    left_positions = [text.find(f"LEFT-{i:02d}") for i in range(20)]
    assert left_positions == sorted(left_positions)
    right_positions = [text.find(f"RIGHT-{i:02d}") for i in range(8)]
    assert right_positions == sorted(right_positions)


def test_pdfplumber_single_column_unchanged():
    """Single-column pages must still extract cleanly — the column
    detector should not invent boundaries on a normal narrative page."""
    from io import BytesIO
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(
            "This is a single column document with sufficient prose "
            "to exercise the detector. " * 10,
            styles["Normal"],
        ),
    ]
    doc.build(story)

    ext = PdfplumberExtractor()
    page = ext.extract_page(buf.getvalue(), 0)
    assert "single column document" in page.text
    # The whole paragraph should appear as one block — no column-break
    # artefact should bisect the prose.
    assert page.text.count("single column document") >= 5


def test_normalize_layout_whitespace_collapses_padding():
    """Layout mode pads with runs of spaces/blank lines — the cleanup
    must collapse them without destroying semantic spacing."""
    raw = "alpha     beta\ngamma   delta\n\n\n\nepsilon zeta\n"
    out = _normalize_layout_whitespace(raw)
    # Runs of >=3 spaces collapsed to one
    assert "alpha beta" in out
    assert "gamma delta" in out
    # Runs of >=3 blank lines collapsed to one blank line
    assert "\n\n\n" not in out
    # Single space and single blank line preserved
    assert "epsilon zeta" in out


def test_normalize_layout_whitespace_keeps_short_runs():
    """Two-space runs must be preserved (could be sentence spacing)."""
    raw = "End of sentence.  Next sentence starts."
    out = _normalize_layout_whitespace(raw)
    assert out == raw
