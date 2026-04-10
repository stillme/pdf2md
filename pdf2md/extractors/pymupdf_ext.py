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

        Two-pass approach:
        1. First pass: determine the dominant body text font size
        2. Second pass: collect bold text that is LARGER than body text
        This prevents author names, table headers, and inline bold from
        being detected as headings.
        """
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise ValueError(f"Invalid PDF: {e}") from e

        # Pass 1: find dominant body text size (most common non-bold font size)
        size_counts: dict[float, int] = {}
        for page_idx in range(min(len(doc), 10)):  # sample first 10 pages
            page = doc[page_idx]
            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []):
                if block.get("type", 0) != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        flags = span.get("flags", 0)
                        is_bold = bool(flags & (1 << 4))
                        font_name = span.get("font", "")
                        if not is_bold and "Bold" not in font_name:
                            size = round(span.get("size", 0), 1)
                            text = span.get("text", "").strip()
                            if len(text) > 10:  # only count substantial text
                                size_counts[size] = size_counts.get(size, 0) + len(text)

        body_size = max(size_counts, key=size_counts.get) if size_counts else 10.0

        # Pass 2: collect bold headings larger than body text
        headings: list[dict] = []

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_dict = page.get_text("dict")

            for block in page_dict.get("blocks", []):
                if block.get("type", 0) != 0:
                    continue

                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue

                    line_text = "".join(s.get("text", "") for s in spans).strip()

                    if len(line_text) < 3 or len(line_text) > 80:
                        continue

                    first_span = spans[0]
                    flags = first_span.get("flags", 0)
                    is_bold = bool(flags & (1 << 4))
                    font_name = first_span.get("font", "")
                    if not is_bold:
                        is_bold = "Bold" in font_name

                    if not is_bold:
                        continue

                    font_size = float(first_span.get("size", 0.0))

                    # Key filter: must be larger than body text OR same size
                    # but with a heading-like font (e.g., Nature uses same-size bold)
                    # Allow same-size bold only if the text looks like a heading
                    # (not a URL, not an author list, not a figure caption)
                    if font_size < body_size - 0.5:
                        continue  # smaller than body = definitely not a heading

                    if not line_text[0].isupper():
                        continue

                    if _SUPERSCRIPT_RE.match(line_text):
                        continue

                    if _AUTHOR_RE.match(line_text):
                        continue

                    # Reject URLs
                    if "http" in line_text.lower() or "www." in line_text.lower():
                        continue

                    # Reject figure/table captions (start with "Fig." or "Table")
                    if re.match(r"^(Fig\.|Figure|Table|Extended Data)", line_text):
                        continue

                    # Reject lines with commas that look like author affiliations
                    if "," in line_text and line_text.count(",") >= 2:
                        continue

                    words = line_text.split()

                    # Reject person-name-like lines (2-3 capitalized words, no
                    # section keywords) — catches single author names like
                    # "William El Sayed" at near-body-size bold
                    if (font_size <= body_size + 1.0
                            and 2 <= len(words) <= 4
                            and all(w[0].isupper() for w in words if w[0].isalpha())
                            and not any(w.lower() in {
                                "abstract", "introduction", "methods", "results",
                                "discussion", "conclusions", "references",
                                "acknowledgements", "online", "content",
                            } for w in words)):
                        # Likely a person name, not a heading
                        continue

                    # Reject lines with email-like patterns or special chars
                    if "✉" in line_text or "@" in line_text:
                        continue

                    if len(words) == 1 and len(line_text) < 4:
                        continue

                    # For same-size-as-body bold, be stricter: require short text
                    # (real headings at body size are typically 2-6 words)
                    if font_size <= body_size + 0.5 and len(words) > 8:
                        continue

                    headings.append({
                        "text": line_text,
                        "page": page_idx,
                        "font_size": font_size,
                    })

        doc.close()
        return headings

    def extract_figures(
        self, pdf_bytes: bytes, min_width: int = 200, min_height: int = 200,
        max_per_page: int | None = 1,
    ) -> list[dict]:
        """Extract significant images from the PDF.

        Returns list of dicts: {"page": int, "image_bytes": bytes, "width": int, "height": int}

        Filters: only images >= min_width x min_height (skips icons, decorations,
        vector fragments).

        When max_per_page is set (default 1), keeps only the largest images per
        page by area. This prevents sub-panels (panels A, B, C of a composite
        figure) from each counting as a separate figure.
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

        # Limit to largest N images per page to avoid counting sub-panels
        # (panels A, B, C of a composite figure) as separate figures.
        if max_per_page is not None:
            by_page: dict[int, list[dict]] = {}
            for fig in figures:
                by_page.setdefault(fig["page"], []).append(fig)
            figures = []
            for page_key in sorted(by_page.keys()):
                page_figs = sorted(
                    by_page[page_key],
                    key=lambda f: f["width"] * f["height"],
                    reverse=True,
                )
                figures.extend(page_figs[:max_per_page])

        return figures
