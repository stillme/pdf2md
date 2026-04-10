"""PyMuPDF extractor (optional dependency)."""

from __future__ import annotations

try:
    import pymupdf
    _PYMUPDF_AVAILABLE = True
except ImportError:
    _PYMUPDF_AVAILABLE = False

from pdf2md.extractors.base import ExtractionResult, PageContent, RawFigure


class PymupdfExtractor:
    """Extractor backed by PyMuPDF (fitz) — fast text + image extraction."""

    def __init__(self) -> None:
        if not _PYMUPDF_AVAILABLE:
            raise ImportError(
                "pymupdf is not installed. "
                "Install it with: pip install pymupdf"
            )

    @property
    def name(self) -> str:
        return "pymupdf"

    @property
    def capabilities(self) -> list[str]:
        return ["text", "images", "tables"]

    def extract(self, pdf_bytes: bytes) -> ExtractionResult:
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise ValueError(f"Invalid PDF: {e}") from e

        pages = []
        for i in range(len(doc)):
            content = self._extract_page(doc, i)
            pages.append(content)
        doc.close()
        return ExtractionResult(pages=pages, engine=self.name)

    def extract_page(self, pdf_bytes: bytes, page_number: int) -> PageContent:
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise ValueError(f"Invalid PDF: {e}") from e

        if page_number < 0 or page_number >= len(doc):
            doc.close()
            raise ValueError(f"Page {page_number} out of range (0-{len(doc) - 1})")

        content = self._extract_page(doc, page_number)
        doc.close()
        return content

    def _extract_page(self, doc: "pymupdf.Document", page_idx: int) -> PageContent:
        page = doc[page_idx]
        text = page.get_text() or ""

        # Extract embedded images
        figures: list[RawFigure] = []
        for img_ref in page.get_images(full=True):
            xref = img_ref[0]
            try:
                img_data = doc.extract_image(xref)
                figures.append(RawFigure(
                    image_bytes=img_data.get("image"),
                    caption=None,
                    bbox=None,
                ))
            except Exception:
                pass

        confidence = 0.85 if len(text) > 50 else 0.3

        return PageContent(
            page_number=page_idx,
            text=text,
            tables=[],
            figures=figures,
            confidence=confidence,
        )
