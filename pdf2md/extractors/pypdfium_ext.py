"""pypdfium2-based text and image extractor (MIT core)."""
from __future__ import annotations
from pdf2md.extractors.base import ExtractionResult, PageContent


class PypdfiumExtractor:
    @property
    def name(self) -> str:
        return "pypdfium2"

    @property
    def capabilities(self) -> list[str]:
        return ["text", "images"]

    def extract(self, pdf_bytes: bytes) -> ExtractionResult:
        raise NotImplementedError("Implemented in Task 6")

    def extract_page(self, pdf_bytes: bytes, page_number: int) -> PageContent:
        raise NotImplementedError("Implemented in Task 6")
