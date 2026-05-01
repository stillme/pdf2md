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


def _is_bold_span(span: dict) -> bool:
    """Return whether a PyMuPDF text span is bold/semibold/heavy/black weight.

    Recognises both the explicit bold flag (PyMuPDF flag bit 4) and a wide
    range of font-name conventions used by scientific publishers:

    - "bold"/"semibold" — most common
    - "heavy"/"black" — Cell-press papers use HelveticaNeue-Heavy for
      section headings; Adobe-Acrobat-encoded Cell papers expose this same
      face as ``AdvPSHN-H`` (the trailing ``-H`` suffix) which we also treat
      as a heavy/bold weight.
    """
    flags = span.get("flags", 0)
    raw_font = span.get("font", "")
    font_name = raw_font.lower()
    if flags & (1 << 4):
        return True
    if "bold" in font_name or "semibold" in font_name:
        return True
    if "heavy" in font_name or "black" in font_name:
        return True
    # Trailing weight suffix used by Adv* / Type1-encoded Cell-press fonts
    # e.g. "AdvPSHN-H" (Heavy), "AdvPSHN-B" (Bold). We accept "-H" or "-B"
    # at the end of the (case-sensitive) font name, but only when the rest
    # of the name is not a regular weight already handled above.
    if raw_font.endswith(("-H", "-B")) and not font_name.endswith(("-r", "-l", "-m")):
        return True
    return False


def _leading_bold_text(spans: list[dict]) -> str:
    """Return the contiguous bold text at the start of a line.

    Tolerates short non-bold "bridge" spans between bold runs:

    - Whitespace-only spans (commonly emitted by PyMuPDF as
      ``GlyphLessFont`` separators between adjacent bold spans).
    - Single-glyph symbol spans (e.g. the ★/✦ in ``STAR★METHODS``,
      which Cell-press encodes as a short span in a symbol font that
      lives between two bold ``HelveticaNeue-Heavy`` words).

    Without these allowances, multi-word bold headings such as
    ``OVERCOMING FUNCTIONAL CHALLENGES`` and ``STAR★METHODS`` would be
    truncated to just the first word.
    """
    parts: list[str] = []
    pending: list[str] = []
    for span in spans:
        text = span.get("text", "")
        if not text:
            continue
        if _is_bold_span(span):
            # bold span: flush any pending bridge spans, then append
            if pending:
                parts.extend(pending)
                pending = []
            parts.append(text)
            continue
        if not parts:
            # haven't started a bold run yet → not a leading-bold line
            break
        # We have an in-progress bold run and a non-bold span.
        # Treat as a bridge if it's whitespace OR a short symbol/punct token.
        stripped = text.strip()
        if stripped == "":
            pending.append(text)
            continue
        # Allow short symbolic glyphs (1-3 chars, no alphanumerics) — these
        # are typically font-encoded ornaments between adjacent bold words.
        if len(stripped) <= 3 and not any(c.isalnum() for c in stripped):
            pending.append(text)
            continue
        # Real non-bold text — bold run ends here, drop pending bridges.
        break
    return "".join(parts).strip()


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

                    line_text = _leading_bold_text(spans)

                    if len(line_text) < 3 or len(line_text) > 80:
                        continue

                    first_span = spans[0]
                    if not _is_bold_span(first_span):
                        continue

                    font_size = float(first_span.get("size", 0.0))

                    # Key filter: must be larger than body text OR same size
                    # but with a heading-like font (e.g., Nature uses same-size bold)
                    # Allow same-size bold only if the text looks like a heading
                    # (not a URL, not an author list, not a figure caption)
                    if font_size < body_size - 0.5:
                        continue  # smaller than body = definitely not a heading
                    if font_size > body_size * 2:
                        continue  # title text, not a section heading

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

        total_pages = len(doc)
        doc.close()

        # Filter out running headers: same heading text appearing on most
        # pages (e.g. "Article", "Review", "Letter" on Cell-press papers).
        if total_pages >= 4 and headings:
            from collections import defaultdict
            pages_by_text: dict[str, set[int]] = defaultdict(set)
            for h in headings:
                pages_by_text[h["text"]].add(h["page"])
            running_headers = {
                txt for txt, pages in pages_by_text.items()
                if len(pages) >= 3 and len(pages) / total_pages >= 0.5
            }
            if running_headers:
                headings = [h for h in headings if h["text"] not in running_headers]

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
