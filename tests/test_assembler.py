"""Tests for markdown assembler."""

import pytest
from pdf2md.assembler import assemble_markdown
from pdf2md.extractors.base import PageContent, RawTable, RawFigure


def test_assemble_basic_text():
    pages = [
        PageContent(page_number=0, text="Hello world.", tables=[], figures=[], confidence=0.9),
    ]
    result = assemble_markdown(pages)
    assert "Hello world." in result.markdown
    assert result.metadata.pages == 1


def test_assemble_detects_headings():
    pages = [
        PageContent(
            page_number=0,
            text="Introduction\nThis is the intro paragraph.\n\nMethods\nWe did the experiment.",
            tables=[], figures=[], confidence=0.9,
        ),
    ]
    result = assemble_markdown(pages)
    assert len(result.sections) >= 2
    titles = [s.title for s in result.sections]
    assert "Introduction" in titles
    assert "Methods" in titles


def test_assemble_includes_tables():
    pages = [
        PageContent(
            page_number=0,
            text="Results\nSee table below.",
            tables=[RawTable(
                markdown="| A | B |\n|---|---|\n| 1 | 2 |",
                headers=["A", "B"],
                rows=[["1", "2"]],
                confidence=0.9,
            )],
            figures=[], confidence=0.9,
        ),
    ]
    result = assemble_markdown(pages)
    assert "| A | B |" in result.markdown
    assert len(result.tables) == 1


def test_assemble_multi_page():
    pages = [
        PageContent(page_number=0, text="Page one content.", tables=[], figures=[], confidence=0.9),
        PageContent(page_number=1, text="Page two content.", tables=[], figures=[], confidence=0.8),
    ]
    result = assemble_markdown(pages)
    assert "Page one content." in result.markdown
    assert "Page two content." in result.markdown
    assert result.metadata.pages == 2
    assert len(result.page_confidences) == 2


def test_assemble_figures_get_ids():
    pages = [
        PageContent(
            page_number=0, text="See figure.",
            tables=[],
            figures=[RawFigure(image_bytes=b"fake", caption="A plot")],
            confidence=0.9,
        ),
    ]
    result = assemble_markdown(pages)
    assert len(result.figures) == 1
    assert result.figures[0].id == "fig1"
    assert result.figures[0].caption == "A plot"


def test_assemble_confidence_is_average():
    pages = [
        PageContent(page_number=0, text="A", tables=[], figures=[], confidence=0.8),
        PageContent(page_number=1, text="B", tables=[], figures=[], confidence=0.6),
    ]
    result = assemble_markdown(pages)
    assert result.confidence == pytest.approx(0.7, abs=0.01)


def test_assemble_strips_headers_footers():
    pages = [
        PageContent(
            page_number=0,
            text="Journal of Examples Vol 1\nIntroduction\nContent here.\n\n1",
            tables=[], figures=[], confidence=0.9,
        ),
        PageContent(
            page_number=1,
            text="Journal of Examples Vol 1\nMore content.\n\n2",
            tables=[], figures=[], confidence=0.9,
        ),
    ]
    result = assemble_markdown(pages)
    assert result.markdown.count("Journal of Examples Vol 1") <= 1


# --- Bug 1: Numbered section headings ---

def test_numbered_headings():
    from pdf2md.assembler import _is_heading
    assert _is_heading("1 Introduction") is not None
    assert _is_heading("2 Methods") is not None
    assert _is_heading("2.1 Data Collection") is not None
    assert _is_heading("3.2.1 Statistical Analysis") is not None
    assert _is_heading("1. Introduction") is not None  # with period
    assert _is_heading("12 Some Long Random Sentence That Is Not A Heading Really") is None


# --- Bug 2: Gene names not headings ---

def test_gene_names_not_headings():
    from pdf2md.assembler import _is_heading
    assert _is_heading("RHOA") is None
    assert _is_heading("SPLICEOSOME") is None
    assert _is_heading("ISCU") is None
    assert _is_heading("MT-TI") is None
    # But real ALL CAPS headings still work
    assert _is_heading("MATERIALS AND METHODS") is not None
    assert _is_heading("RESULTS AND DISCUSSION") is not None


# --- Bug 3: Table text deduplication ---

def test_no_duplicate_table_text():
    """Table cell values should not appear both as inline text and in the markdown table."""
    pages = [
        PageContent(
            page_number=0,
            text="Results\nTable 1 shows the results.\nCondition Mean SD p-value\nControl 12.3 2.1 -\nTreatment A 18.7 3.4 0.002",
            tables=[RawTable(
                markdown="| Condition | Mean | SD | p-value |\n|---|---|---|---|\n| Control | 12.3 | 2.1 | - |\n| Treatment A | 18.7 | 3.4 | 0.002 |",
                headers=["Condition", "Mean", "SD", "p-value"],
                rows=[["Control", "12.3", "2.1", "-"], ["Treatment A", "18.7", "3.4", "0.002"]],
                confidence=0.9,
            )],
            figures=[], confidence=0.9,
        ),
    ]
    result = assemble_markdown(pages)
    lines = result.markdown.split('\n')
    non_table_lines = [l for l in lines if not l.startswith('|') and not l.startswith('---')]
    non_table_text = '\n'.join(non_table_lines)
    # The inline text rows like "Control 12.3 2.1 -" should be stripped
    # since they duplicate the markdown table content
    assert "Control 12.3" not in non_table_text, "Table row text duplicated outside markdown table"
    assert "Treatment A 18.7" not in non_table_text, "Table row text duplicated outside markdown table"


def test_figure_panel_labels_not_headings():
    from pdf2md.assembler import _is_heading
    assert _is_heading("SPF GF FMT") is None
    assert _is_heading("AB CD AB CD AB CD") is None
    assert _is_heading("WT KO WT KO") is None
    # But real short headings still work
    assert _is_heading("Discussion") is not None


def test_repeated_headers_deduped():
    """Running headers that appear as section titles on many pages should be deduped.

    Simulates even pages in a math paper where the page number is first, then the
    running header — so _detect_repeated_lines does not catch it as a first/last line.
    """
    pages = []
    for i in range(6):
        # Page number is the first line; running header is the second line.
        # This bypasses _detect_repeated_lines (which only looks at first/last lines)
        # but _is_heading still detects the ALL-CAPS multi-word running header.
        pages.append(PageContent(
            page_number=i,
            text=f"{i+2}\nDG FOR THE EMI MODEL\nSome content on page {i}.",
            tables=[], figures=[], confidence=0.9,
        ))
    result = assemble_markdown(pages)
    titles = [s.title for s in result.sections]
    # "DG FOR THE EMI MODEL" should appear at most once
    assert titles.count("DG FOR THE EMI MODEL") <= 1


# --- Bold heading detection ---

def test_bold_headings_used():
    """Bold headings passed to assemble_markdown should become sections."""
    pages = [
        PageContent(
            page_number=0,
            text="Some text about the spatial transcriptome.",
            tables=[], figures=[], confidence=0.9,
        ),
        PageContent(
            page_number=1,
            text="More text about robustness.",
            tables=[], figures=[], confidence=0.9,
        ),
    ]
    bold_headings = [
        {"text": "Constructing the spatial transcriptome", "page": 0, "font_size": 8.2},
        {"text": "The intestinal landscape is robust", "page": 1, "font_size": 8.2},
    ]
    result = assemble_markdown(pages, bold_headings=bold_headings)
    titles = [s.title for s in result.sections]
    assert "Constructing the spatial transcriptome" in titles
    assert "The intestinal landscape is robust" in titles


def test_bold_headings_no_duplicates_with_regex():
    """Bold headings that match existing regex headings should not create duplicates."""
    pages = [
        PageContent(
            page_number=0,
            text="Introduction\nSome intro text.",
            tables=[], figures=[], confidence=0.9,
        ),
    ]
    bold_headings = [
        {"text": "Introduction", "page": 0, "font_size": 10.0},
    ]
    result = assemble_markdown(pages, bold_headings=bold_headings)
    titles = [s.title for s in result.sections]
    assert titles.count("Introduction") == 1


def test_bold_headings_none_is_noop():
    """Passing no bold_headings should work the same as before."""
    pages = [
        PageContent(
            page_number=0,
            text="Introduction\nSome text.",
            tables=[], figures=[], confidence=0.9,
        ),
    ]
    result_without = assemble_markdown(pages)
    result_with = assemble_markdown(pages, bold_headings=None)
    assert len(result_without.sections) == len(result_with.sections)


# --- Hyphen handling ---

def test_clean_hyphens_preserves_compound_words():
    """Compound words at line breaks should keep the hyphen."""
    from pdf2md.assembler import _clean_hyphens
    assert _clean_hyphens("microbiota-\ndriven") == "microbiota-driven"
    assert _clean_hyphens("region-\nenriched") == "region-enriched"
    assert _clean_hyphens("single-\ncell") == "single-cell"
    assert _clean_hyphens("immune-\nmediated") == "immune-mediated"
    assert _clean_hyphens("well-\ncharacterized") == "well-characterized"


def test_clean_hyphens_joins_combining_prefixes():
    """Latin/Greek combining forms at line breaks should join without hyphen."""
    from pdf2md.assembler import _clean_hyphens
    assert _clean_hyphens("immuno-\nlogical") == "immunological"
    assert _clean_hyphens("physio-\nlogical") == "physiological"
    assert _clean_hyphens("neuro-\ninflammation") == "neuroinflammation"
    assert _clean_hyphens("gastro-\nintestinal") == "gastrointestinal"
    assert _clean_hyphens("macro-\nphages") == "macrophages"


def test_clean_hyphens_joins_suffix_continuations():
    """Words broken at suffix boundaries should rejoin without hyphen."""
    from pdf2md.assembler import _clean_hyphens
    assert _clean_hyphens("environ-\nmental") == "environmental"
    assert _clean_hyphens("transcrip-\ntional") == "transcriptional"
    assert _clean_hyphens("express-\ning") == "expressing"
    assert _clean_hyphens("differ-\nentiation") == "differentiation"


def test_clean_hyphens_still_removes_soft_hyphens():
    """Soft hyphens (U+00AD) should still be removed."""
    from pdf2md.assembler import _clean_hyphens
    assert _clean_hyphens("immuno\xadlogical") == "immunological"
    assert _clean_hyphens("soft\xadhyphen") == "softhyphen"


def test_clean_hyphens_in_assembled_output():
    """Compound words should survive assembly intact."""
    pages = [
        PageContent(
            page_number=0,
            text="We identified a microbiota-\ndriven adaptation in the region-\nenriched colon.",
            tables=[], figures=[], confidence=0.9,
        ),
    ]
    result = assemble_markdown(pages)
    assert "microbiota-driven" in result.markdown
    assert "region-enriched" in result.markdown
