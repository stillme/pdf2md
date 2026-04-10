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
