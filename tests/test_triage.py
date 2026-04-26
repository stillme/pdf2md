"""Tests for triage — page analysis and engine routing."""

from pdf2md.triage.analyzer import analyze_page, PageAnalysis
from pdf2md.triage.router import select_engine, select_tier
from pdf2md.config import Tier


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
