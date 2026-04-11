"""Page confidence scoring — measures extraction completeness, not just text presence.

A page's confidence reflects whether we successfully captured what the page contains:
- Text pages: readable text with sentence structure
- Figure pages: image extracted (and ideally captioned)
- Table pages: table parsed with headers and rows
- Mixed pages: weighted combination

This replaces the crude `0.85 if len(text) > 50 else 0.3` heuristic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pdf2md.document import Document, Figure


# ── Sentence structure detection (lightweight) ─────────────────────────

_SENTENCE_WORDS = frozenset({
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'have', 'has', 'had',
    'in', 'on', 'at', 'to', 'for', 'with', 'from', 'by', 'of', 'and',
    'or', 'but', 'that', 'which', 'this', 'we', 'our', 'not', 'been',
})


def _text_has_sentences(text: str) -> bool:
    """Check if text contains at least one sentence-like structure."""
    words = text.lower().split()
    hits = sum(1 for w in words if w.strip('.,;:!?()') in _SENTENCE_WORDS)
    return hits >= 3


# ── Per-page scoring ───────────────────────────────────────────────────

@dataclass
class PageSignals:
    """Raw signals extracted from a page for confidence scoring."""
    text_chars: int = 0
    has_sentences: bool = False
    figure_count: int = 0
    figure_bytes: int = 0
    table_count: int = 0
    table_rows: int = 0
    is_figure_page: bool = False


def _score_text(signals: PageSignals) -> float:
    """Score text extraction quality (0-1)."""
    if signals.text_chars == 0:
        return 0.0
    if signals.text_chars < 50:
        return 0.2
    if not signals.has_sentences:
        # Has text but no sentence structure — might be garbled or just metadata
        return 0.5
    # Substantial text with sentence structure
    if signals.text_chars > 500:
        return 1.0
    return 0.7 + 0.3 * min(signals.text_chars / 500, 1.0)


def _score_figures(signals: PageSignals) -> float:
    """Score figure extraction quality (0-1)."""
    if signals.figure_count == 0:
        return 0.0
    # At least one figure extracted — check if it has substance
    if signals.figure_bytes > 10_000:
        return 1.0  # Substantial image data
    if signals.figure_bytes > 1_000:
        return 0.8
    return 0.5  # Tiny image — might be decorative


def _score_tables(signals: PageSignals) -> float:
    """Score table extraction quality (0-1)."""
    if signals.table_count == 0:
        return 0.0
    if signals.table_rows > 0:
        return 1.0  # Table with data rows
    return 0.6  # Table headers but no rows


def score_page(signals: PageSignals) -> float:
    """Compute page confidence from extraction signals.

    Uses a weighted combination based on what content the page appears to have.
    A page that is primarily a figure should be scored on figure extraction,
    not penalized for having little text.
    """
    text_score = _score_text(signals)
    figure_score = _score_figures(signals)
    table_score = _score_tables(signals)

    # Determine page type and weight accordingly
    has_text = signals.text_chars > 50
    has_figures = signals.figure_count > 0
    has_tables = signals.table_count > 0

    if signals.is_figure_page:
        # Page is dominated by a figure — weight figure heavily
        if has_text:
            return figure_score * 0.6 + text_score * 0.4
        return figure_score * 0.85 + 0.15  # Base credit for being a valid figure page

    if has_text and has_figures and has_tables:
        return text_score * 0.5 + figure_score * 0.3 + table_score * 0.2
    if has_text and has_figures:
        return text_score * 0.6 + figure_score * 0.4
    if has_text and has_tables:
        return text_score * 0.6 + table_score * 0.4
    if has_text:
        return text_score
    if has_figures:
        return figure_score * 0.85 + 0.15
    if has_tables:
        return table_score

    # Empty page
    return 0.0


# ── Document-level rescoring ───────────────────────────────────────────

def rescore_document(doc: Document, page_texts: list[str]) -> Document:
    """Rescore page confidences based on actual extraction results.

    Called after assembly with the per-page extracted text and the final
    Document (which has figures, tables, sections assigned to pages).

    Returns a new Document with updated confidence and page_confidences.
    """
    # Build a map of which pages have figures
    figure_pages: dict[int, list[Figure]] = {}
    for fig in doc.figures:
        figure_pages.setdefault(fig.page, []).append(fig)

    # Build a map of which pages have tables
    table_pages: dict[int, int] = {}
    for tbl in doc.tables:
        table_pages[tbl.page] = table_pages.get(tbl.page, 0) + len(tbl.rows)

    # Score each page
    page_confidences: list[float] = []

    for i, text in enumerate(page_texts):
        figs = figure_pages.get(i, [])

        # Calculate total figure bytes (from base64 length as proxy)
        fig_bytes = sum(
            len(f.image_base64) if f.image_base64 else 0
            for f in figs
        )

        # Detect if this is a figure-dominated page:
        # little text but has a figure, or figure takes most of the page
        is_figure_page = (
            len(figs) > 0
            and len(text.strip()) < 300
            and fig_bytes > 5_000
        )

        signals = PageSignals(
            text_chars=len(text.strip()),
            has_sentences=_text_has_sentences(text),
            figure_count=len(figs),
            figure_bytes=fig_bytes,
            table_count=1 if i in table_pages else 0,
            table_rows=table_pages.get(i, 0),
            is_figure_page=is_figure_page,
        )

        page_confidences.append(round(score_page(signals), 3))

    # Overall confidence: weighted average giving more weight to text pages
    # (they carry the bulk of the content)
    if not page_confidences:
        overall = 0.0
    else:
        overall = sum(page_confidences) / len(page_confidences)

    return doc.model_copy(update={
        "confidence": round(overall, 4),
        "page_confidences": page_confidences,
    })
