"""VLM direct extractor — renders PDF pages as images, sends to VLM for markdown extraction."""

from __future__ import annotations

import re
from io import BytesIO

import pypdfium2 as pdfium

from pdf2md.extractors.base import ExtractionResult, PageContent, RawTable
from pdf2md.providers.base import VLMProvider

# DPI for rendering pages as images
_RENDER_DPI = 200

_EXTRACTION_PROMPT = """\
You are a precise document extraction system. Convert this PDF page image to clean markdown.

Rules:
- Reproduce ALL text content faithfully — do not summarize or omit anything.
- Use proper markdown headings (# ## ###) matching the document hierarchy.
- Format tables as markdown tables with | delimiters and --- separator rows.
- Preserve LaTeX equations using $ for inline and $$ for display math.
- Maintain paragraph structure with blank lines between paragraphs.
- Do NOT add any commentary, explanation, or metadata — output ONLY the page content as markdown.
- If the page contains figures, note them as ![Figure description](figure) placeholders.

Output the markdown now:"""


def _render_page_to_png(pdf_bytes: bytes, page_number: int, dpi: int = _RENDER_DPI) -> bytes:
    """Render a single PDF page to PNG bytes using pypdfium2."""
    pdf = pdfium.PdfDocument(pdf_bytes)
    if page_number < 0 or page_number >= len(pdf):
        pdf.close()
        raise ValueError(f"Page {page_number} out of range (0-{len(pdf) - 1})")

    page = pdf[page_number]
    scale = dpi / 72  # 72 is the default PDF DPI
    bitmap = page.render(scale=scale)
    pil_image = bitmap.to_pil()
    page.close()
    pdf.close()

    buf = BytesIO()
    pil_image.save(buf, format="PNG")
    return buf.getvalue()


def _parse_tables_from_markdown(text: str) -> list[RawTable]:
    """Extract markdown tables from VLM output into RawTable objects."""
    tables: list[RawTable] = []

    # Match markdown table blocks: header row, separator row, data rows
    table_pattern = re.compile(
        r"(\|[^\n]+\|\n)"        # header row
        r"(\|[\s\-:|]+\|\n)"     # separator row
        r"((?:\|[^\n]+\|\n?)*)",  # data rows
        re.MULTILINE,
    )

    for match in table_pattern.finditer(text):
        full_table = match.group(0).strip()
        lines = full_table.splitlines()
        if len(lines) < 2:
            continue

        # Parse header
        header_line = lines[0]
        headers = [cell.strip() for cell in header_line.strip("|").split("|")]

        # Parse data rows (skip separator at index 1)
        rows: list[list[str]] = []
        for row_line in lines[2:]:
            if row_line.strip():
                cells = [cell.strip() for cell in row_line.strip("|").split("|")]
                rows.append(cells)

        tables.append(RawTable(
            markdown=full_table,
            headers=headers,
            rows=rows,
            confidence=0.7,
        ))

    return tables


class VLMExtractor:
    """Extractor that renders PDF pages as images and uses a VLM for direct markdown extraction."""

    def __init__(self, provider: VLMProvider) -> None:
        self._provider = provider

    @property
    def name(self) -> str:
        return "vlm"

    @property
    def capabilities(self) -> list[str]:
        return ["text", "tables", "layout", "ocr"]

    def extract(self, pdf_bytes: bytes) -> ExtractionResult:
        """Extract all pages from a PDF using VLM."""
        pdf = pdfium.PdfDocument(pdf_bytes)
        num_pages = len(pdf)
        pdf.close()

        pages: list[PageContent] = []
        for i in range(num_pages):
            pages.append(self.extract_page(pdf_bytes, i))

        return ExtractionResult(pages=pages, engine=self.name)

    def extract_page(self, pdf_bytes: bytes, page_number: int) -> PageContent:
        """Render a page to PNG and send to VLM for markdown extraction."""
        # Render page to PNG image
        image_bytes = _render_page_to_png(pdf_bytes, page_number)

        # Send image + prompt to VLM
        markdown_text = self._provider.complete_sync(
            _EXTRACTION_PROMPT,
            image=image_bytes,
        )

        # Parse any tables from the VLM response
        tables = _parse_tables_from_markdown(markdown_text)

        return PageContent(
            page_number=page_number,
            text=markdown_text,
            tables=tables,
            figures=[],
            confidence=0.7,  # VLM extraction gets baseline 0.7 confidence
        )
