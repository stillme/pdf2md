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
