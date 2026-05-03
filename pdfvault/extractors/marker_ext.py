"""Marker-pdf extractor (optional dependency)."""

from __future__ import annotations

import io

try:
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered
    _MARKER_AVAILABLE = True
except ImportError:
    _MARKER_AVAILABLE = False

from pdfvault.extractors.base import ExtractionResult, PageContent, RawTable


class MarkerExtractor:
    """Extractor backed by marker-pdf (high-quality OCR + layout)."""

    def __init__(self) -> None:
        if not _MARKER_AVAILABLE:
            raise ImportError(
                "marker-pdf is not installed. "
                "Install it with: pip install marker-pdf"
            )
        self._models = create_model_dict()

    @property
    def name(self) -> str:
        return "marker"

    @property
    def capabilities(self) -> list[str]:
        return ["text", "tables", "ocr", "figures"]

    def extract(self, pdf_bytes: bytes) -> ExtractionResult:
        converter = PdfConverter(artifact_dict=self._models)
        try:
            rendered = converter(io.BytesIO(pdf_bytes))
        except Exception as exc:
            raise RuntimeError(
                f"marker extraction failed ({type(exc).__name__}: {exc}). "
                "This may be a surya/torch model issue on non-GPU hardware."
            ) from exc
        full_text, _, _ = text_from_rendered(rendered)

        # Split text by page markers if present, otherwise treat as single page
        pages = self._split_into_pages(full_text)
        return ExtractionResult(pages=pages, engine=self.name)

    def extract_page(self, pdf_bytes: bytes, page_number: int) -> PageContent:
        result = self.extract(pdf_bytes)
        if page_number < 0 or page_number >= len(result.pages):
            raise ValueError(f"Page {page_number} out of range (0-{len(result.pages) - 1})")
        return result.pages[page_number]

    def _split_into_pages(self, full_text: str) -> list[PageContent]:
        """Split marker output into per-page PageContent objects."""
        # Marker may include form-feed (\f) as page separators
        if "\f" in full_text:
            page_texts = full_text.split("\f")
        else:
            page_texts = [full_text]

        pages = []
        for i, text in enumerate(page_texts):
            text = text.strip()
            confidence = 0.90 if len(text) > 50 else 0.3
            pages.append(PageContent(
                page_number=i,
                text=text,
                tables=[],
                figures=[],
                confidence=confidence,
            ))
        return pages
