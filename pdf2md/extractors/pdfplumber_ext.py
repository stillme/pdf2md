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
        text = page.extract_text() or ""

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
