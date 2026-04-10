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
