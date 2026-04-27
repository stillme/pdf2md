"""pdfplumber-based table extractor (MIT core)."""

from __future__ import annotations

import io
import re

import pdfplumber

from pdf2md.extractors.base import ExtractionResult, PageContent, RawTable

_NUMERIC_RE = re.compile(r"^[\s\-+()$%]*\d[\d.,\s%]*[\s\-+()$%]*$")


def _table_confidence(headers: list[str], rows: list[list[str]]) -> float:
    """Score a table 0-1 from padding ratio, column variance, header sanity, and shape."""
    if not headers or not rows:
        return 0.2
    n_cols = len(headers)
    score = 1.0
    if n_cols < 2:
        score -= 0.4
    if len(rows) < 2:
        score -= 0.4
    # Column variance: rows that don't match header width
    ragged = sum(1 for r in rows if len(r) != n_cols)
    if ragged:
        score -= 0.15 + min(0.35, 0.35 * ragged / max(1, len(rows)))
    # Padding ratio: empty cells / total cells (across header + rows)
    cells = [c for r in [headers] + rows for c in r]
    if cells:
        empty = sum(1 for c in cells if not c.strip())
        score -= min(0.5, (empty / len(cells)) * 0.7)
    # Header sanity: numeric-looking header cells suggest data-as-header
    non_empty_headers = [h for h in headers if h.strip()]
    if non_empty_headers:
        numeric = sum(1 for h in non_empty_headers if _NUMERIC_RE.match(h.strip()))
        if numeric / len(non_empty_headers) > 0.5:
            score -= 0.3
    return max(0.0, min(1.0, score))


# Collapse the heavy whitespace padding introduced by pdfplumber's
# ``layout=True`` mode while preserving semantic spacing. Layout mode pads
# columns with runs of spaces and inserts blank lines for vertical gaps; we
# only flatten obvious noise (3+ spaces -> 1 space, 3+ blank lines -> 1 blank
# line) so downstream cleaners see something close to normal prose.
_RUN_OF_SPACES_RE = re.compile(r" {3,}")
_RUN_OF_BLANK_LINES_RE = re.compile(r"(?:[ \t]*\n){3,}")


def _normalize_layout_whitespace(text: str) -> str:
    if not text:
        return text
    text = _RUN_OF_SPACES_RE.sub(" ", text)
    text = _RUN_OF_BLANK_LINES_RE.sub("\n\n", text)
    # Strip trailing spaces left at the end of lines by layout padding.
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text


# --- Column-aware text extraction ---------------------------------------
#
# ``layout=True`` preserves spatial padding but doesn't actually split a
# physical line that spans multiple columns. On Nature- / Cell-style
# 2-column journals the columns are close enough that words from the
# right column glue onto words from the left column on every line. The
# downstream cost of that is brutal:
#
# * "faecal microbiota transplant" gets split as "faecal micro-" (end
#   of left column) + "biota transplant" (start of right column),
#   producing a dangling hyphen the cleaner can't rejoin.
# * Bibliography entries from facing columns merge onto one line, so
#   the parser sees ``[3] Hickey ... Nature 41. Xu ...`` and treats
#   the second author block as ref-3's continuation.
# * Heatmap axis labels in figure regions leak into the text stream
#   alongside body prose.
#
# The fix here detects column boundaries from the x-distribution of
# words, crops each column's bbox, extracts text per-column with
# ``layout=True`` to preserve in-column line order, then concatenates
# top-to-bottom column-by-column. arXiv-style wide-gap layouts are also
# handled — the threshold tolerates either.

# Minimum horizontal gap (in PDF points) that counts as a column
# boundary. Nature's tight two-column body produces gaps of ~10pt;
# arXiv-style papers run ~30-50pt. 8pt is above any inter-word slack
# we've measured and below the narrowest real column gap on the
# corpus. Single-column pages produce zero empty runs in the text
# region, so a lower threshold doesn't cause false positives there.
_MIN_COLUMN_GAP_PT = 8.0
# Minimum word count on a page before we trust the gap-detection at all.
# Sparse pages (title pages, blank back matter) don't have enough data
# to cluster reliably.
_COLUMN_MIN_WORDS = 60
# Each side of a candidate boundary must hold at least this fraction of
# the page's words. Without this, a single-column page with a sparse
# strip near one margin produces a "boundary" that bisects narrative
# text instead of separating real columns. 20% is permissive enough to
# cover end-of-section pages where one column is much shorter than the
# other (very common on Nature/Cell layouts).
_MIN_COLUMN_FILL_FRACTION = 0.20


def _detect_column_boundaries(page) -> list[float]:
    """Return x-coordinates of column splits on ``page``, ascending.

    Empty list means the page is single-column (or too sparse to split).

    Spatial-occupancy approach: build a 1pt-resolution histogram of
    which x-coordinates have any word covering them, then find the
    longest contiguous empty interval inside the text-bearing region.
    A real column gap is a vertical strip that NO word crosses — single-
    column pages don't have one because line wrapping fills the page
    width. The midpoint-sort approach is fooled by sparse line wraps.
    """
    try:
        words = page.extract_words()
    except Exception:
        return []
    if len(words) < _COLUMN_MIN_WORDS:
        return []

    page_width = int(round(float(page.width)))
    if page_width <= 0:
        return []

    # 1pt-resolution occupancy: covered[x] = True if any word's bbox
    # spans the integer column x. Words can have fractional bboxes;
    # rounding outward (floor x0, ceil x1) avoids missing tight gaps.
    import math
    covered = [False] * (page_width + 1)
    for w in words:
        x0 = max(0, int(math.floor(w["x0"])))
        x1 = min(page_width, int(math.ceil(w["x1"])))
        for x in range(x0, x1 + 1):
            covered[x] = True

    # Bound the search to the text-bearing region — anything outside is
    # margin and would produce a huge spurious gap.
    try:
        text_min = max(0, int(math.floor(min(w["x0"] for w in words))))
        text_max = min(page_width, int(math.ceil(max(w["x1"] for w in words))))
    except ValueError:
        return []
    if text_max - text_min < 2 * _MIN_COLUMN_GAP_PT:
        return []

    # Walk the text-bearing range, find the longest run of False.
    longest_run = 0
    longest_start = -1
    longest_end = -1
    run_start = -1
    for x in range(text_min, text_max + 1):
        if not covered[x]:
            if run_start < 0:
                run_start = x
            run_len = x - run_start + 1
            if run_len > longest_run:
                longest_run = run_len
                longest_start = run_start
                longest_end = x
        else:
            run_start = -1

    if longest_run < _MIN_COLUMN_GAP_PT:
        return []

    boundary = (longest_start + longest_end) / 2.0

    # Both columns must actually contain text. Sparse stragglers near
    # one margin can produce a "boundary" that bisects narrative prose.
    left_count = sum(1 for w in words if (w["x0"] + w["x1"]) / 2 < boundary)
    right_count = len(words) - left_count
    threshold = int(len(words) * _MIN_COLUMN_FILL_FRACTION)
    if left_count < threshold or right_count < threshold:
        return []

    return [boundary]


def _extract_text_with_columns(page) -> str:
    """Extract page text, splitting at detected column boundaries.

    Single-column pages fall back to the plain ``layout=True`` extract.
    Multi-column pages are cropped per-column and concatenated in
    reading order (left to right). Within each column we still use
    ``layout=True`` so vertical line order is preserved.
    """
    boundaries = _detect_column_boundaries(page)
    if not boundaries:
        return _normalize_layout_whitespace(page.extract_text(layout=True) or "")

    # bbox is (x0, top, x1, bottom). Build [0, b1, b2, ..., width].
    edges = [0.0] + boundaries + [float(page.width)]
    column_texts: list[str] = []
    for i in range(len(edges) - 1):
        bbox = (edges[i], 0.0, edges[i + 1], float(page.height))
        try:
            cropped = page.crop(bbox)
            text = cropped.extract_text(layout=True) or ""
        except Exception:
            text = ""
        text = _normalize_layout_whitespace(text)
        if text.strip():
            column_texts.append(text)
    return "\n\n".join(column_texts)


class PdfplumberExtractor:
    @property
    def name(self) -> str:
        return "pdfplumber"

    @property
    def capabilities(self) -> list[str]:
        return ["text", "tables"]

    def extract(self, pdf_bytes: bytes) -> ExtractionResult:
        try:
            pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
        except Exception as e:
            raise ValueError(f"Invalid PDF: {e}") from e

        pages = []
        for i, page in enumerate(pdf.pages):
            content = self._extract_page(page, i)
            pages.append(content)
        pdf.close()
        return ExtractionResult(pages=pages, engine=self.name)

    def extract_page(self, pdf_bytes: bytes, page_number: int) -> PageContent:
        try:
            pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
        except Exception as e:
            raise ValueError(f"Invalid PDF: {e}") from e

        if page_number < 0 or page_number >= len(pdf.pages):
            pdf.close()
            raise ValueError(f"Page {page_number} out of range")

        content = self._extract_page(pdf.pages[page_number], page_number)
        pdf.close()
        return content

    def _extract_page(self, page, page_idx: int) -> PageContent:
        # Column-aware extraction. Detects multi-column layouts via the
        # x-distribution of word midpoints, then extracts each column
        # bbox independently so right-column text doesn't glue onto
        # left-column lines. Falls back transparently to plain
        # ``layout=True`` extraction on single-column pages.
        text = _extract_text_with_columns(page)

        tables = []
        raw_tables = page.extract_tables() or []

        for raw_table in raw_tables:
            if not raw_table or len(raw_table) < 2:
                continue

            headers = [str(cell or "").strip() for cell in raw_table[0]]
            rows = [
                [str(cell or "").strip() for cell in row]
                for row in raw_table[1:]
            ]

            markdown = self._table_to_markdown(headers, rows)
            tables.append(RawTable(
                markdown=markdown, headers=headers, rows=rows,
                confidence=_table_confidence(headers, rows),
            ))

        confidence = 0.8 if len(text) > 50 else 0.3

        return PageContent(
            page_number=page_idx, text=text, tables=tables, figures=[], confidence=confidence,
        )

    def _table_to_markdown(self, headers: list[str], rows: list[list[str]]) -> str:
        if not headers:
            return ""
        header_line = "| " + " | ".join(headers) + " |"
        sep_line = "| " + " | ".join("---" for _ in headers) + " |"
        data_lines = []
        for row in rows:
            padded = row + [""] * (len(headers) - len(row))
            data_lines.append("| " + " | ".join(padded[:len(headers)]) + " |")
        return "\n".join([header_line, sep_line] + data_lines)
