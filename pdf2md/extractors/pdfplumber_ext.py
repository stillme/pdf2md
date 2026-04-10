"""pdfplumber-based table extractor (MIT core)."""
from __future__ import annotations
from pdf2md.extractors.base import ExtractionResult, PageContent


class PdfplumberExtractor:
    @property
    def name(self) -> str:
        return "pdfplumber"

    @property
    def capabilities(self) -> list[str]:
        return ["text", "tables"]

    def extract(self, pdf_bytes: bytes) -> ExtractionResult:
        raise NotImplementedError("Implemented in Task 7")

    def extract_page(self, pdf_bytes: bytes, page_number: int) -> PageContent:
        raise NotImplementedError("Implemented in Task 7")
