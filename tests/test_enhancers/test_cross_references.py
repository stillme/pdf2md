"""Tests for cross-reference linking."""

from __future__ import annotations

from pdfvault.document import (
    Document,
    Figure,
    FigureIndexEntry,
    Metadata,
    Section,
)
from pdfvault.enhancers.cross_references import add_cross_references


def _doc(
    markdown: str,
    *,
    figures: list[Figure] | None = None,
    figure_index: list[FigureIndexEntry] | None = None,
    sections: list[Section] | None = None,
) -> Document:
    return Document(
        markdown=markdown,
        metadata=Metadata(pages=1),
        figures=figures or [],
        figure_index=figure_index or [],
        sections=sections or [],
    )


def _fig_index(
    figure_id: str,
    number: int,
    *,
    is_extended: bool = False,
) -> FigureIndexEntry:
    label = ("Extended Data Fig." if is_extended else "Fig.") + f" {number}"
    return FigureIndexEntry(
        figure_id=figure_id,
        label=label,
        figure_number=number,
        is_extended=is_extended,
        page=1,
        markdown_anchor=figure_id,
    )


# --- Figures -------------------------------------------------------------


def test_figure_mention_linked():
    """`see Fig. 1` becomes a link to the fig-1 anchor."""
    md = "see Fig. 1 for details.\n\n![Fig. 1 | Caption text.](fig1)"
    figures = [Figure(id="fig1", page=1)]
    figure_index = [_fig_index("fig1", 1)]
    doc = _doc(md, figures=figures, figure_index=figure_index)

    out = add_cross_references(md, doc)

    assert "[Fig. 1](#fig-1)" in out
    # Anchor is injected before the marker.
    assert '<a id="fig-1"></a>' in out
    # Caption alt text inside the marker is left alone (skipped as caption).
    assert "![Fig. 1 | Caption text.](fig1)" in out


def test_panel_reference_kept():
    """`Fig. 3a` keeps the panel suffix in the link text."""
    md = "see Fig. 3a for the heatmap.\n\n![Fig. 3 | Heatmap.](fig3)"
    figures = [Figure(id="fig3", page=1)]
    figure_index = [_fig_index("fig3", 3)]
    doc = _doc(md, figures=figures, figure_index=figure_index)

    out = add_cross_references(md, doc)

    assert "[Fig. 3a](#fig-3)" in out


def test_extended_data_figure_linked():
    md = "see Extended Data Fig. 2 for the supplement.\n\n![Extended Data Fig. 2 | Foo.](fig2)"
    figures = [Figure(id="fig2", page=1)]
    figure_index = [_fig_index("fig2", 2, is_extended=True)]
    doc = _doc(md, figures=figures, figure_index=figure_index)

    out = add_cross_references(md, doc)

    assert "[Extended Data Fig. 2](#extended-data-fig-2)" in out
    assert '<a id="extended-data-fig-2"></a>' in out


def test_extended_data_mention_does_not_get_nested_inner_link():
    """Regression: ``Extended Data Fig. 1e`` was producing
    ``[Extended Data [Fig. 1e](#fig-1)](#extended-data-fig-1)`` because the
    ``Fig.`` pattern re-matched inside the ``Extended Data Fig.`` pattern's
    output. Renderers fail on nested links AND the inner anchor is wrong
    (``#fig-1`` should be ``#extended-data-fig-1``)."""
    md = (
        "as shown in Extended Data Fig. 1e and elsewhere.\n\n"
        "![Extended Data Fig. 1 | Caption.](fig-ext-1)"
    )
    figures = [Figure(id="fig-ext-1", page=1)]
    figure_index = [_fig_index("fig-ext-1", 1, is_extended=True)]
    doc = _doc(md, figures=figures, figure_index=figure_index)

    out = add_cross_references(md, doc)

    # The single, correct link must be present.
    assert "[Extended Data Fig. 1e](#extended-data-fig-1)" in out
    # The buggy nested form must NOT appear in any variation.
    assert "[Extended Data [Fig." not in out
    assert "](#fig-1)](#extended-data-fig-1)" not in out


def test_extended_data_panel_range_does_not_nest():
    """Range panels like ``Extended Data Fig. 5d,e`` and ``Fig. 2b–d``
    must also rewrite as a single link with the panel suffix preserved."""
    md = (
        "see Extended Data Fig. 5d,e for the timecourse and "
        "Fig. 2b–d for the controls.\n\n"
        "![Fig. 2 | Controls.](fig2)\n\n"
        "![Extended Data Fig. 5 | Timecourse.](fig-ext-5)"
    )
    figures = [Figure(id="fig2", page=1), Figure(id="fig-ext-5", page=2)]
    figure_index = [
        _fig_index("fig2", 2),
        _fig_index("fig-ext-5", 5, is_extended=True),
    ]
    doc = _doc(md, figures=figures, figure_index=figure_index)

    out = add_cross_references(md, doc)

    assert "[Extended Data Fig. 5d,e](#extended-data-fig-5)" in out
    assert "[Fig. 2b–d](#fig-2)" in out
    # Neither should be wrapped in another link.
    assert "[Extended Data [Fig." not in out
    assert "[[Fig." not in out


def test_figure_word_does_not_shadow_fig_period():
    """``Figure 3`` and ``Fig. 3`` both link, neither wraps the other."""
    md = (
        "Figure 3 explains the model; see also Fig. 3 for details.\n\n"
        "![Fig. 3 | Model.](fig3)"
    )
    figures = [Figure(id="fig3", page=1)]
    figure_index = [_fig_index("fig3", 3)]
    doc = _doc(md, figures=figures, figure_index=figure_index)

    out = add_cross_references(md, doc)

    assert "[Figure 3](#fig-3)" in out
    assert "[Fig. 3](#fig-3)" in out
    # No nesting of one inside the other.
    assert "[Figure [Fig." not in out
    assert "[Fig. [Figure" not in out


# --- Sections ------------------------------------------------------------


def test_section_mention_linked():
    """`Section 4` resolves only when a numbered heading exists."""
    md = "as in Section 4 we describe the method."
    sections = [Section(level=1, title="4 Methods", content="", page=1)]
    doc = _doc(md, sections=sections)

    out = add_cross_references(md, doc)

    assert "[Section 4](#4-methods)" in out


def test_section_mention_skipped_when_missing():
    """Without a matching numbered section, the mention is left as plain text."""
    md = "as in Section 4 we describe the method."
    sections = [Section(level=1, title="Methods", content="", page=1)]
    doc = _doc(md, sections=sections)

    out = add_cross_references(md, doc)

    assert "Section 4" in out
    assert "](#" not in out  # no link emitted at all


# --- Citations -----------------------------------------------------------


def _references_doc(prose: str) -> Document:
    md = (
        f"{prose}\n\n"
        "## References\n\n"
        "[12] Smith, J. Foo. 2020.\n"
        "[13] Jones, K. Bar. 2021.\n"
        "[14] Lee, H. Baz. 2022.\n"
    )
    return _doc(md)


def test_citation_list_expanded():
    doc = _references_doc("As shown previously [12,13,14] this works.")

    out = add_cross_references(doc.markdown, doc)

    assert "[[12](#ref-12),[13](#ref-13),[14](#ref-14)]" in out


def test_citation_range_expanded():
    doc = _references_doc("As shown previously [12-14] this works.")

    out = add_cross_references(doc.markdown, doc)

    assert "[[12](#ref-12),[13](#ref-13),[14](#ref-14)]" in out


def test_citation_single():
    doc = _references_doc("As shown previously [13] this works.")

    out = add_cross_references(doc.markdown, doc)

    assert "[[13](#ref-13)]" in out


def test_citation_skipped_when_no_references():
    """No bibliography parsed -> citations stay as plain text."""
    md = "As shown previously [12,13] this works."
    doc = _doc(md)

    out = add_cross_references(md, doc)

    assert out == md


def test_citation_inside_bibliography_not_relinked():
    """References lines must not be rewritten back onto themselves."""
    doc = _references_doc("Trivial body.")

    out = add_cross_references(doc.markdown, doc)

    # Each reference entry is anchored, but the leading [12] is not rewritten
    # into [[12](#ref-12)].
    assert '<a id="ref-12"></a>[12] Smith' in out
    assert "[[12](#ref-12)] Smith" not in out


def test_bibliography_anchors_added():
    doc = _references_doc("Body.")

    out = add_cross_references(doc.markdown, doc)

    assert '<a id="ref-12"></a>' in out
    assert '<a id="ref-13"></a>' in out
    assert '<a id="ref-14"></a>' in out


# --- Skip-range behaviour ------------------------------------------------


def test_caption_not_double_linked():
    """A caption block referencing another figure is left untouched."""
    md = (
        "see Fig. 1 in the body.\n\n"
        "![Fig. 1 | A](fig1)\n\n"
        "Fig. 1 | Caption text mentioning Fig. 2 inline.\n\n"
        "![Fig. 2 | B](fig2)\n"
    )
    figures = [Figure(id="fig1", page=1), Figure(id="fig2", page=1)]
    figure_index = [_fig_index("fig1", 1), _fig_index("fig2", 2)]
    doc = _doc(md, figures=figures, figure_index=figure_index)

    out = add_cross_references(md, doc)

    # Body mention -> linked.
    assert "see [Fig. 1](#fig-1) in the body." in out
    # Caption line itself -> NOT linked.
    assert "Fig. 1 | Caption text mentioning Fig. 2 inline." in out
    # Specifically no link inside the caption line.
    caption_line = next(
        line for line in out.split("\n") if line.startswith("Fig. 1 | Caption")
    )
    assert "](#fig-2)" not in caption_line


# --- Misc ----------------------------------------------------------------


def test_no_change_when_no_match():
    """Doc with figures but no body mention: markdown is unchanged."""
    md = "Just some prose with no figure mentions."
    figures = [Figure(id="fig1", page=1)]
    figure_index = [_fig_index("fig1", 1)]
    doc = _doc(md, figures=figures, figure_index=figure_index)

    out = add_cross_references(md, doc)

    assert out == md


def test_empty_markdown():
    doc = _doc("")
    assert add_cross_references("", doc) == ""


def test_no_figures_no_sections_no_refs():
    """Total degenerate doc -> no errors, no changes."""
    md = "Just see Fig. 3 and Section 4 and [12]."
    doc = _doc(md)

    out = add_cross_references(md, doc)

    assert out == md
