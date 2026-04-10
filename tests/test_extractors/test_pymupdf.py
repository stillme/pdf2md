"""Tests for PyMuPDF extractor."""
import pytest

try:
    import pymupdf
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


@pytest.mark.skipif(not HAS_PYMUPDF, reason="pymupdf not installed")
class TestPymupdfExtractor:
    def test_name(self):
        from pdf2md.extractors.pymupdf_ext import PymupdfExtractor
        ext = PymupdfExtractor()
        assert ext.name == "pymupdf"

    def test_extract(self, sample_pdf_bytes):
        from pdf2md.extractors.pymupdf_ext import PymupdfExtractor
        ext = PymupdfExtractor()
        result = ext.extract(sample_pdf_bytes)
        assert result.engine == "pymupdf"
        assert len(result.pages) == 2
        assert "Introduction" in result.pages[0].text

    def test_extract_page(self, sample_pdf_bytes):
        from pdf2md.extractors.pymupdf_ext import PymupdfExtractor
        ext = PymupdfExtractor()
        page = ext.extract_page(sample_pdf_bytes, 1)
        assert "Discussion" in page.text

    def test_extract_bold_headings(self, sample_pdf_bytes):
        from pdf2md.extractors.pymupdf_ext import PymupdfExtractor
        ext = PymupdfExtractor()
        headings = ext.extract_bold_headings(sample_pdf_bytes)
        assert isinstance(headings, list)
        # Sample PDF uses reportlab Heading1 style which should be detected
        titles = [h["text"] for h in headings]
        assert any("Introduction" in t for t in titles) or any("Results" in t for t in titles)

    def test_extract_bold_headings_have_page_and_font_size(self, sample_pdf_bytes):
        from pdf2md.extractors.pymupdf_ext import PymupdfExtractor
        ext = PymupdfExtractor()
        headings = ext.extract_bold_headings(sample_pdf_bytes)
        for h in headings:
            assert "text" in h
            assert "page" in h
            assert "font_size" in h
            assert isinstance(h["page"], int)
            assert isinstance(h["font_size"], float)

    def test_extract_figures(self, sample_pdf_bytes):
        from pdf2md.extractors.pymupdf_ext import PymupdfExtractor
        ext = PymupdfExtractor()
        figures = ext.extract_figures(sample_pdf_bytes)
        assert isinstance(figures, list)
        # Sample PDF may or may not have large images, but shouldn't error
