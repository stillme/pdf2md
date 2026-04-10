"""pdfplumber-based table extractor (MIT core)."""

from __future__ import annotations

import io

import pdfplumber

from pdf2md.extractors.base import ExtractionResult, PageContent, RawTable


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
                markdown=markdown, headers=headers, rows=rows, confidence=0.8,
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
