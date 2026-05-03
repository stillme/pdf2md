"""Tests for triage — page analysis and engine routing."""

from pdfvault.triage.analyzer import analyze_page, PageAnalysis
from pdfvault.triage.router import select_engine, select_tier
from pdfvault.config import Tier


def test_analyze_page_native_text(sample_pdf_bytes):
    analysis = analyze_page(sample_pdf_bytes, page_number=0)
    assert isinstance(analysis, PageAnalysis)
    assert analysis.has_text_layer is True
    assert analysis.text_coverage > 0.5
    assert analysis.is_scanned is False


def test_analyze_page_detects_tables(sample_pdf_bytes):
    analysis = analyze_page(sample_pdf_bytes, page_number=0)
    assert analysis.has_tables is True


def test_analyze_page_2_no_tables(sample_pdf_bytes):
    analysis = analyze_page(sample_pdf_bytes, page_number=1)
    assert analysis.has_tables is False


def test_select_tier_auto_native_text(sample_pdf_bytes):
    analysis = analyze_page(sample_pdf_bytes, page_number=0)
    tier = select_tier(analysis, requested=Tier.AUTO)
    assert tier in (Tier.FAST, Tier.STANDARD)


def test_select_tier_override():
    analysis = PageAnalysis(
        page_number=0, has_text_layer=True, text_coverage=0.9,
        is_scanned=False, has_tables=False, has_images=False,
        has_equations=False, complexity_score=0.2,
    )
    tier = select_tier(analysis, requested=Tier.DEEP)
    assert tier == Tier.DEEP


def test_select_engine_fast_tier():
    engines = select_engine(Tier.FAST, has_text_layer=True, available_engines=["pypdfium2", "pdfplumber"])
    assert engines[0] == "pypdfium2"


def test_select_engine_includes_pdfplumber_for_tables():
    engines = select_engine(Tier.FAST, has_text_layer=True, available_engines=["pypdfium2", "pdfplumber"], has_tables=True)
    assert "pdfplumber" in engines


def test_select_engine_prefers_marker_when_available():
    engines = select_engine(
        Tier.STANDARD, has_text_layer=False,
        available_engines=["pypdfium2", "pdfplumber", "marker"],
    )
    assert engines[0] == "marker"


def test_select_engine_scanned_with_vlm():
    engines = select_engine(
        Tier.STANDARD,
        has_text_layer=False,
        available_engines=["pypdfium2", "pdfplumber", "marker"],
        is_scanned=True,
        vlm_available=True,
    )
    assert engines[0] == "vlm"


def test_select_engine_scanned_without_vlm():
    engines = select_engine(
        Tier.STANDARD,
        has_text_layer=False,
        available_engines=["pypdfium2", "pdfplumber", "marker"],
        is_scanned=True,
        vlm_available=False,
    )
    assert "vlm" not in engines
    assert engines[0] == "marker"


def test_select_engine_scanned_fast_tier_skips_vlm():
    engines = select_engine(
        Tier.FAST,
        has_text_layer=False,
        available_engines=["pypdfium2", "pdfplumber"],
        is_scanned=True,
        vlm_available=True,
    )
    assert "vlm" not in engines


def test_select_engine_native_text_with_vlm():
    engines = select_engine(
        Tier.STANDARD,
        has_text_layer=True,
        available_engines=["pypdfium2", "pdfplumber", "marker"],
        is_scanned=False,
        vlm_available=True,
    )
    assert "vlm" not in engines


# --- Synthetic scanned-PDF detection ---------------------------------
#
# Regression tests for the ``is_scanned`` detection path. The triage
# layer used to call ``pdfium.FPDF_PAGEOBJ_IMAGE`` (which doesn't exist
# at the package root in current pypdfium2) inside a broad ``except
# Exception`` block, so ``has_images`` was always False and therefore
# ``is_scanned`` was always False. Routing for scanned pages went to
# pdfplumber, which produced empty markdown. These tests guard against
# that regression by feeding the analyzer a synthetic image-only PDF.


def test_analyze_page_detects_scanned(scanned_pdf_bytes):
    """Image-only page should be flagged as scanned with no text layer."""
    analysis = analyze_page(scanned_pdf_bytes, page_number=0)
    assert analysis.has_text_layer is False
    assert analysis.has_images is True, (
        "image detection regressed — analyzer missed the page raster. "
        "Check pypdfium2 constant import and get_objects(max_depth=...)."
    )
    assert analysis.is_scanned is True
    # Coverage is 0 because there's no embedded text at all.
    assert analysis.text_coverage == 0.0


def test_select_tier_auto_routes_scanned_to_standard(scanned_pdf_bytes):
    """Auto tier should bump scanned pages up to STANDARD so VLM can fire."""
    analysis = analyze_page(scanned_pdf_bytes, page_number=0)
    tier = select_tier(analysis, requested=Tier.AUTO)
    assert tier == Tier.STANDARD


def test_select_engine_routes_scanned_pdf_to_vlm(scanned_pdf_bytes):
    """End-to-end triage: scanned PDF + VLM available -> vlm engine first."""
    analysis = analyze_page(scanned_pdf_bytes, page_number=0)
    engines = select_engine(
        Tier.STANDARD,
        has_text_layer=analysis.has_text_layer,
        available_engines=["pypdfium2", "pdfplumber"],
        has_tables=analysis.has_tables,
        is_scanned=analysis.is_scanned,
        vlm_available=True,
    )
    assert engines[0] == "vlm"
