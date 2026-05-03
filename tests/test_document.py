"""Tests for the Document model."""

import json

from pdfvault.document import (
    Document, Metadata, Section, Figure, FigureIndexEntry, FigureMention,
    Table, Equation, Reference,
)


def test_metadata_defaults():
    m = Metadata(pages=5)
    assert m.title is None
    assert m.authors == []
    assert m.pages == 5


def test_section_creation():
    s = Section(level=1, title="Introduction", content="Some text.", page=1)
    assert s.level == 1
    assert s.title == "Introduction"


def test_figure_creation():
    f = Figure(id="fig1", page=1, confidence=0.9)
    assert f.caption is None
    assert f.description is None
    assert f.confidence == 0.9


def test_figure_index_entry_creation():
    entry = FigureIndexEntry(
        figure_id="fig1",
        label="Fig. 1",
        figure_number=1,
        page=2,
        caption="A mapped result.",
        panels=["a", "b"],
        mentions=[FigureMention(panels=["a"], context="As shown in Fig. 1a")],
        markdown_anchor="fig1",
        parse_confidence=0.9,
    )
    assert entry.label == "Fig. 1"
    assert entry.mentions[0].panels == ["a"]


def test_table_creation():
    t = Table(
        id="tab1",
        markdown="| A | B |\n|---|---|\n| 1 | 2 |",
        headers=["A", "B"],
        rows=[["1", "2"]],
        page=1,
        confidence=0.95,
    )
    assert len(t.headers) == 2
    assert len(t.rows) == 1


def test_equation_creation():
    e = Equation(id="eq1", latex=r"E = mc^2", inline=False, page=1)
    assert e.latex == r"E = mc^2"
    assert not e.inline


def test_reference_creation():
    r = Reference(id="[1]", authors=["Smith J"], title="A paper", year="2024")
    assert r.authors == ["Smith J"]


def test_document_creation():
    doc = Document(
        markdown="# Title\n\nSome text.",
        metadata=Metadata(title="Test", pages=1),
        sections=[Section(level=1, title="Title", content="Some text.", page=1)],
        figures=[],
        tables=[],
        equations=[],
        bibliography=[],
        confidence=0.95,
        page_confidences=[0.95],
        engine_used="pypdfium2",
        tier_used="fast",
        processing_time_ms=42,
    )
    assert doc.confidence == 0.95
    assert doc.engine_used == "pypdfium2"
    assert len(doc.sections) == 1


def test_document_save_markdown(tmp_path):
    doc = Document(
        markdown="# Title\n\nContent here.",
        metadata=Metadata(pages=1),
        sections=[], figures=[], tables=[], equations=[], bibliography=[],
        confidence=0.9, page_confidences=[0.9],
        engine_used="pypdfium2", tier_used="fast", processing_time_ms=10,
    )
    out = tmp_path / "output.md"
    doc.save_markdown(str(out))
    assert out.read_text() == "# Title\n\nContent here."


def test_document_save_json(tmp_path):
    doc = Document(
        markdown="# Title",
        metadata=Metadata(title="Test", pages=1),
        sections=[], figures=[], tables=[], equations=[], bibliography=[],
        confidence=0.9, page_confidences=[0.9],
        engine_used="pypdfium2", tier_used="fast", processing_time_ms=10,
    )
    out = tmp_path / "output.json"
    doc.save_json(str(out))
    data = json.loads(out.read_text())
    assert data["metadata"]["title"] == "Test"
    assert data["engine_used"] == "pypdfium2"


def test_document_save_figure_index(tmp_path):
    doc = Document(
        markdown="# Title",
        metadata=Metadata(title="Test", doi="10.123/test", pages=1),
        figure_index=[
            FigureIndexEntry(
                figure_id="fig1",
                label="Fig. 1",
                figure_number=1,
                page=0,
                caption="Caption.",
                markdown_anchor="fig1",
            ),
        ],
        confidence=0.9,
        page_confidences=[0.9],
        engine_used="pypdfium2",
        tier_used="fast",
        processing_time_ms=10,
    )
    out = tmp_path / "figures.json"
    doc.save_figure_index(str(out))
    data = json.loads(out.read_text())
    assert data["schema_version"] == "pdfvault.figure_index.v1"
    assert data["document"]["doi"] == "10.123/test"
    assert data["figures"][0]["figure_id"] == "fig1"
