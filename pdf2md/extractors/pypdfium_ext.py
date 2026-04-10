"""pypdfium2-based text and image extractor (MIT core)."""

from __future__ import annotations

import pypdfium2 as pdfium

from pdf2md.extractors.base import ExtractionResult, PageContent, RawFigure


class PypdfiumExtractor:
    @property
    def name(self) -> str:
        return "pypdfium2"

    @property
    def capabilities(self) -> list[str]:
        return ["text", "images"]

    def extract(self, pdf_bytes: bytes) -> ExtractionResult:
        try:
            pdf = pdfium.PdfDocument(pdf_bytes)
        except Exception as e:
            raise ValueError(f"Invalid PDF: {e}") from e

        pages = []
        for i in range(len(pdf)):
            page_content = self._extract_single_page(pdf, i)
            pages.append(page_content)
        pdf.close()
        return ExtractionResult(pages=pages, engine=self.name)

    def extract_page(self, pdf_bytes: bytes, page_number: int) -> PageContent:
        try:
            pdf = pdfium.PdfDocument(pdf_bytes)
        except Exception as e:
            raise ValueError(f"Invalid PDF: {e}") from e

        if page_number < 0 or page_number >= len(pdf):
            pdf.close()
            raise ValueError(f"Page {page_number} out of range (0-{len(pdf) - 1})")

        content = self._extract_single_page(pdf, page_number)
        pdf.close()
        return content

    def _extract_single_page(self, pdf: pdfium.PdfDocument, page_idx: int) -> PageContent:
        page = pdf[page_idx]

        textpage = page.get_textpage()
        text = textpage.get_text_range()
        textpage.close()

        width, height = page.get_size()
        page_area = width * height
        # Baseline: ~0.0006 chars/pt² represents a normally-dense text page.
        # Dividing actual density by the baseline gives a ratio ≥ 1 for
        # content-rich pages, clamped to 1.0.
        baseline_density = page_area * 0.0006
        text_density = len(text) / max(baseline_density, 1)
        confidence = min(text_density, 1.0)

        figures = self._extract_images(page)
        page.close()

        return PageContent(
            page_number=page_idx,
            text=text,
            tables=[],
            figures=figures,
            confidence=confidence,
        )

    def render_page(self, pdf_bytes: bytes, page_number: int, dpi: int = 150) -> bytes:
        """Render a full page as PNG. Used as figure fallback when individual images can't be extracted."""
        from io import BytesIO
        pdf = pdfium.PdfDocument(pdf_bytes)
        if page_number < 0 or page_number >= len(pdf):
            pdf.close()
            raise ValueError(f"Page {page_number} out of range (0-{len(pdf) - 1})")
        page = pdf[page_number]
        scale = dpi / 72
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
        page.close()
        pdf.close()
        buf = BytesIO()
        pil_image.save(buf, format="PNG")
        return buf.getvalue()

    def _extract_images(self, page: pdfium.PdfPage) -> list[RawFigure]:
        figures = []
        try:
            for obj in page.get_objects():
                if obj.type == pdfium.FPDF_PAGEOBJ_IMAGE:
                    try:
                        bitmap = obj.get_bitmap()
                        pil_image = bitmap.to_pil()
                        if pil_image.width >= 50 and pil_image.height >= 50:
                            from io import BytesIO
                            buf = BytesIO()
                            pil_image.save(buf, format="PNG")
                            figures.append(RawFigure(image_bytes=buf.getvalue()))
                    except Exception:
                        pass
        except Exception:
            pass
        return figures
