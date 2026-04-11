"""Tests for the confidence scoring module."""

from pdf2md.confidence import PageSignals, score_page, rescore_document
from pdf2md.document import Document, Figure, Metadata, Table


def test_text_page_high_confidence():
    """A page with substantial text and sentence structure should score high."""
    signals = PageSignals(
        text_chars=2000,
        has_sentences=True,
        figure_count=0,
        figure_bytes=0,
        table_count=0,
        table_rows=0,
        is_figure_page=False,
    )
    assert score_page(signals) >= 0.95


def test_figure_page_high_confidence():
    """A figure-dominated page with a large image should score high."""
    signals = PageSignals(
        text_chars=50,
        has_sentences=False,
        figure_count=1,
        figure_bytes=500_000,
        table_count=0,
        table_rows=0,
        is_figure_page=True,
    )
    assert score_page(signals) >= 0.85


def test_empty_page_zero():
    """An empty page should score 0."""
    signals = PageSignals()
    assert score_page(signals) == 0.0


def test_garbled_text_low_confidence():
    """Text without sentence structure should score lower than real prose."""
    garbled = PageSignals(text_chars=200, has_sentences=False)
    prose = PageSignals(text_chars=200, has_sentences=True)
    assert score_page(garbled) < score_page(prose)


def test_mixed_page():
    """A page with text, figures, and tables should weight all components."""
    signals = PageSignals(
        text_chars=1000,
        has_sentences=True,
        figure_count=1,
        figure_bytes=100_000,
        table_count=1,
        table_rows=5,
        is_figure_page=False,
    )
    score = score_page(signals)
    assert 0.8 <= score <= 1.0


def test_figure_page_not_penalized():
    """Figure pages should NOT get a low score just because they lack text."""
    # This is the key test — the old heuristic gave 0.3 to these pages
    signals = PageSignals(
        text_chars=20,  # Minimal text (just a caption reference)
        has_sentences=False,
        figure_count=1,
        figure_bytes=1_000_000,  # Large figure image
        table_count=0,
        table_rows=0,
        is_figure_page=True,
    )
    score = score_page(signals)
    assert score >= 0.85, f"Figure page scored {score}, should be >= 0.85"


def test_rescore_document_updates_confidences():
    """rescore_document should replace page confidences with content-aware scores."""
    doc = Document(
        markdown="Some text\n![Figure 1](fig1)\n",
        metadata=Metadata(pages=2),
        figures=[Figure(id="fig1", page=1, image_base64="A" * 100_000)],
        confidence=0.5,
        page_confidences=[0.85, 0.3],  # Old heuristic values
    )
    page_texts = [
        "The intestine is characterized by an environment in which host requirements are paired.",
        "Extended Data Fig. 1",  # Figure page — minimal text
    ]

    rescored = rescore_document(doc, page_texts)

    # Text page should be reasonable (short text = ~0.75, not 0.3 or 0.0)
    assert rescored.page_confidences[0] >= 0.7

    # Figure page should be HIGH (not the old 0.3 penalty)
    assert rescored.page_confidences[1] >= 0.85

    # Overall should be much higher than the old 0.5
    assert rescored.confidence >= 0.8


def test_table_page_confidence():
    """Pages with tables should get credit for table extraction."""
    doc = Document(
        markdown="| A | B |\n|---|---|\n| 1 | 2 |\n",
        metadata=Metadata(pages=1),
        tables=[Table(id="tbl1", page=0, headers=["A", "B"], rows=[["1", "2"]])],
        confidence=0.3,
        page_confidences=[0.3],
    )
    page_texts = ["Some header text"]

    rescored = rescore_document(doc, page_texts)
    assert rescored.page_confidences[0] >= 0.6
