"""Page-level complexity analysis for triage."""

from __future__ import annotations
import io
from pydantic import BaseModel


class PageAnalysis(BaseModel):
    page_number: int
    has_text_layer: bool = False
    text_coverage: float = 0.0
    is_scanned: bool = False
    has_tables: bool = False
    has_images: bool = False
    has_equations: bool = False
    complexity_score: float = 0.0


def analyze_page(pdf_bytes: bytes, page_number: int) -> PageAnalysis:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    if page_number >= len(pdf):
        pdf.close()
        raise ValueError(f"Page {page_number} out of range")

    page = pdf[page_number]
    textpage = page.get_textpage()
    text = textpage.get_text_range()
    textpage.close()

    has_text = len(text.strip()) > 20
    width, height = page.get_size()
    page_area = width * height
    expected_chars = page_area * 0.0006  # calibrated for typical text density
    text_coverage = min(len(text) / max(expected_chars, 1), 1.0)

    # Image detection. Two historical bugs to avoid here:
    #   1. ``pdfium.FPDF_PAGEOBJ_IMAGE`` is not exposed at the package
    #      root in current pypdfium2; the constant lives in
    #      ``pypdfium2.raw``. The previous code raised AttributeError
    #      which the broad ``except`` silently swallowed, so
    #      ``has_images`` was always False — which in turn meant
    #      ``is_scanned`` (defined as ``not has_text and has_images``)
    #      was always False. Scanned pages would silently route to
    #      pdfplumber/pypdfium and produce empty markdown.
    #   2. ``page.get_objects()`` defaults to ``max_depth=2`` which
    #      does not recurse into Form XObjects. Reportlab and many
    #      real-world scanners wrap the page raster in a Form XObject,
    #      so the shallow walk missed it.
    from pypdfium2 import raw as _pdfium_raw
    has_images = False
    try:
        for obj in page.get_objects(max_depth=10):
            if obj.type == _pdfium_raw.FPDF_PAGEOBJ_IMAGE:
                has_images = True
                break
    except Exception:
        pass

    page.close()
    pdf.close()

    has_tables = False
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as plumber_pdf:
            if page_number < len(plumber_pdf.pages):
                plumber_page = plumber_pdf.pages[page_number]
                tables = plumber_page.find_tables()
                has_tables = len(tables) > 0
    except Exception:
        pass

    is_scanned = not has_text and has_images

    complexity = 0.0
    if has_tables:
        complexity += 0.3
    if has_images:
        complexity += 0.2
    if is_scanned:
        complexity += 0.4
    if text_coverage < 0.3:
        complexity += 0.1

    return PageAnalysis(
        page_number=page_number,
        has_text_layer=has_text,
        text_coverage=text_coverage,
        is_scanned=is_scanned,
        has_tables=has_tables,
        has_images=has_images,
        has_equations=False,
        complexity_score=min(complexity, 1.0),
    )
