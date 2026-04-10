"""PyMuPDF extractor (optional dependency)."""

from __future__ import annotations

import re

try:
    import pymupdf
    _PYMUPDF_AVAILABLE = True
except ImportError:
    _PYMUPDF_AVAILABLE = False

from pdf2md.extractors.base import ExtractionResult, PageContent, RawFigure

# Pattern to reject author-like lines (e.g. "John Smith, Jane Doe, Bob Lee")
_AUTHOR_RE = re.compile(r"^[A-Z][a-z]+ [A-Z][a-z]+(?:,\s*[A-Z][a-z]+ [A-Z][a-z]+)+")
# Pattern for superscript annotations or footnote markers
_SUPERSCRIPT_RE = re.compile(r"^\d+[,\s\d]*$")


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

    def extract_bold_headings(self, pdf_bytes: bytes) -> list[dict]:
        """Extract bold text lines that are likely section headings.

        Returns list of dicts: {"text": str, "page": int, "font_size": float}

        Heuristic: a bold span is a heading candidate if:
        - It's on its own line (not inline bold within a paragraph)
        - It's 3-80 chars
        - It starts with uppercase
        - It doesn't look like an author name (no commas with multiple segments)
        - It's not a number or superscript annotation
        """
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise ValueError(f"Invalid PDF: {e}") from e

        headings: list[dict] = []

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_dict = page.get_text("dict")

            for block in page_dict.get("blocks", []):
                # Only text blocks (type 0), not images (type 1)
                if block.get("type", 0) != 0:
                    continue

                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue

                    # Build the full line text from all spans
                    line_text = "".join(s.get("text", "") for s in spans).strip()

                    # Length filter: 3-80 chars
                    if len(line_text) < 3 or len(line_text) > 80:
                        continue

                    # Check if the first span is bold
                    # PyMuPDF flags: bit 4 (value 16) = bold
                    first_span = spans[0]
                    flags = first_span.get("flags", 0)
                    is_bold = bool(flags & (1 << 4))

                    # Also check font name for "Bold" or "Semibold" as fallback
                    font_name = first_span.get("font", "")
                    if not is_bold:
                        is_bold = "Bold" in font_name or "Semibold" in font_name

                    if not is_bold:
                        continue

                    # Must start with uppercase letter
                    if not line_text[0].isupper():
                        continue

                    # Reject pure numbers / superscript annotations
                    if _SUPERSCRIPT_RE.match(line_text):
                        continue

                    # Reject author-like lines
                    if _AUTHOR_RE.match(line_text):
                        continue

                    # Reject single short words (< 4 chars, likely labels)
                    words = line_text.split()
                    if len(words) == 1 and len(line_text) < 4:
                        continue

                    font_size = float(first_span.get("size", 0.0))

                    headings.append({
                        "text": line_text,
                        "page": page_idx,
                        "font_size": font_size,
                    })

        doc.close()
        return headings

    def extract_figures(
        self, pdf_bytes: bytes, min_width: int = 200, min_height: int = 200
    ) -> list[dict]:
        """Extract significant images from the PDF.

        Returns list of dicts: {"page": int, "image_bytes": bytes, "width": int, "height": int}

        Filters: only images >= min_width x min_height (skips icons, decorations,
        vector fragments).
        """
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise ValueError(f"Invalid PDF: {e}") from e

        figures: list[dict] = []
        seen_xrefs: set[int] = set()

        for page_idx in range(len(doc)):
            page = doc[page_idx]

            for img_ref in page.get_images(full=True):
                xref = img_ref[0]

                # Deduplicate across pages (same image can appear on multiple pages)
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                try:
                    img_data = doc.extract_image(xref)
                    width = img_data.get("width", 0)
                    height = img_data.get("height", 0)
                    image_bytes = img_data.get("image")

                    if width >= min_width and height >= min_height and image_bytes:
                        figures.append({
                            "page": page_idx,
                            "image_bytes": image_bytes,
                            "width": width,
                            "height": height,
                        })
                except Exception:
                    pass

        doc.close()
        return figures
