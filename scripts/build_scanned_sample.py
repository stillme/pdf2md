"""Generate a synthetic ``scanned-sample.pdf`` for the test corpus.

Renders a short text passage to a PNG via PIL, then embeds that PNG as the
sole content of a single-page PDF via reportlab. The resulting PDF has NO
text layer — ``page.extract_text()`` returns the empty string — so it
exercises the triage ``is_scanned`` path and forces routing to the VLM
extractor when standard/deep tier is requested.

Run with ``uv run python scripts/build_scanned_sample.py``. The output
lands at ``test_pdfs/scanned-sample.pdf`` (~30 KB).
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


# Short, distinctive text. We assert on a substring of this in the
# end-to-end VLM check so a real OCR pass is required.
PAGE_TEXT = [
    "SCANNED SAMPLE DOCUMENT",
    "",
    "Abstract",
    "",
    "This page exists only as a raster image.",
    "There is no embedded text layer, so any",
    "selectable-text extractor will return an",
    "empty string for this page. The pdf2md",
    "triage layer should detect this case and",
    "route extraction through the VLM engine.",
    "",
    "Introduction",
    "",
    "The quick brown fox jumps over the lazy dog.",
    "Pack my box with five dozen liquor jugs.",
    "",
    "Keywords: triage, OCR, vision-language model.",
]


def _render_text_to_png(width_px: int = 1700, height_px: int = 2200) -> bytes:
    """Render ``PAGE_TEXT`` to a high-contrast grayscale PNG.

    The size matches a US Letter page rendered at ~200 DPI, which is
    well within the legibility band for any modern VLM.
    """
    img = Image.new("L", (width_px, height_px), color=255)
    draw = ImageDraw.Draw(img)

    # Try a couple of common system fonts before falling back to PIL's
    # bitmap default. The default font is tiny (~10 px) which the VLM
    # can still read but looks like a thumbnail; we prefer a real TTF.
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont
    body_font: ImageFont.ImageFont | ImageFont.FreeTypeFont
    title_font: ImageFont.ImageFont | ImageFont.FreeTypeFont
    try:
        title_font = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc", size=44
        )
        body_font = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc", size=32
        )
    except OSError:
        try:
            title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", size=44)
            body_font = ImageFont.truetype("DejaVuSans.ttf", size=32)
        except OSError:
            title_font = ImageFont.load_default()
            body_font = title_font

    margin_x = 140
    y = 180
    for i, line in enumerate(PAGE_TEXT):
        font = title_font if i == 0 else body_font
        draw.text((margin_x, y), line, fill=0, font=font)
        # Roughly 1.5x line height; the title row gets extra spacing.
        y += 64 if i == 0 else 48

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def build_scanned_pdf(out_path: Path) -> None:
    """Write a single-page PDF whose only content is a PNG image."""
    page_w, page_h = letter
    img_bytes = _render_text_to_png()

    # ``reportlab`` won't accept raw PNG bytes for ``drawImage`` without a
    # filename or PIL handle, so we wrap the PNG in a PIL Image and pass
    # that through (the canvas.ImageReader path).
    from reportlab.lib.utils import ImageReader

    reader = ImageReader(BytesIO(img_bytes))

    c = canvas.Canvas(str(out_path), pagesize=letter)
    # Draw the image to fill the page minus a small margin so the page
    # has some white border (more realistic than edge-to-edge scans).
    margin = 0.25 * inch
    c.drawImage(
        reader,
        margin,
        margin,
        width=page_w - 2 * margin,
        height=page_h - 2 * margin,
        preserveAspectRatio=True,
        anchor="c",
    )
    c.showPage()
    c.save()


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "test_pdfs" / "scanned-sample.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    build_scanned_pdf(out)
    size_kb = out.stat().st_size / 1024
    print(f"Wrote {out} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
