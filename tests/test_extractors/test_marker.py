"""Tests for Marker extractor (optional dependency)."""
import pytest

try:
    from marker.converters.pdf import PdfConverter
    HAS_MARKER = True
except ImportError:
    HAS_MARKER = False


@pytest.mark.skipif(not HAS_MARKER, reason="marker-pdf not installed")
class TestMarkerExtractor:
    def test_marker_name(self):
        from pdf2md.extractors.marker_ext import MarkerExtractor
        ext = MarkerExtractor()
        assert ext.name == "marker"

    def test_marker_capabilities(self):
        from pdf2md.extractors.marker_ext import MarkerExtractor
        ext = MarkerExtractor()
        assert "text" in ext.capabilities
        assert "tables" in ext.capabilities
        assert "ocr" in ext.capabilities


def test_marker_import_error_when_not_installed():
    """Marker extractor should raise ImportError cleanly when marker-pdf is missing."""
    if HAS_MARKER:
        pytest.skip("marker-pdf is installed")
    from pdf2md.extractors.marker_ext import MarkerExtractor
    with pytest.raises(ImportError, match="marker-pdf"):
        MarkerExtractor()
