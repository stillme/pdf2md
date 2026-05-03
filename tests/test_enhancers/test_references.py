"""Tests for the bibliography parser."""

from __future__ import annotations

from pdfvault.enhancers.references import (
    parse_references,
    _parse_apa,
    _parse_nature,
    _parse_vancouver,
    _split_top_level,
)


def test_no_references_section_returns_empty() -> None:
    md = "# Title\n\nSome body text without a bibliography."
    assert parse_references(md) == []


def test_empty_references_section_returns_empty() -> None:
    md = "# Title\n\n## References\n\n"
    assert parse_references(md) == []


def test_parses_vancouver_bracketed_entries() -> None:
    md = (
        "## References\n\n"
        "[1] Smith J, Jones K. Title of paper. Journal Name. 2023;45(2):100-110.\n"
        "[2] Lee S, Park H. Another title. Other Journal. 2022;30:15-22.\n"
    )

    refs = parse_references(md)

    assert len(refs) == 2
    first, second = refs
    assert first.id == "ref-1"
    assert first.authors == ["Smith J", "Jones K"]
    assert first.title == "Title of paper"
    assert first.journal == "Journal Name"
    assert first.year == "2023"
    assert first.volume == "45"
    assert first.pages == "100-110"
    assert first.confidence > 0.7

    assert second.id == "ref-2"
    assert second.year == "2022"
    assert second.volume == "30"
    assert second.pages == "15-22"


def test_parses_nature_dotted_entries() -> None:
    md = (
        "## References\n\n"
        "1. Smith, J. & Jones, K. Title of paper. J. Name 45, 100-110 (2023).\n"
        "2. Lee, S., Park, H. & Kim, J. Long title here. Nature 612, 88-95 (2022).\n"
    )

    refs = parse_references(md)

    assert len(refs) == 2
    first, second = refs
    assert first.year == "2023"
    assert first.volume == "45"
    assert first.pages == "100-110"
    assert "Smith, J." in first.authors
    assert "Jones, K." in first.authors
    assert second.volume == "612"
    assert "Lee, S." in second.authors
    assert "Park, H." in second.authors
    assert "Kim, J." in second.authors


def test_parses_apa_entries() -> None:
    md = (
        "## References\n\n"
        "1. Smith, J., & Jones, K. (2023). Title of paper. Journal Name, 45(2), 100-110.\n"
    )
    refs = parse_references(md)
    assert len(refs) == 1
    ref = refs[0]
    assert ref.year == "2023"
    assert ref.title == "Title of paper"
    assert ref.journal == "Journal Name"
    assert ref.volume == "45"
    assert ref.pages == "100-110"
    assert any(a.startswith("Smith") for a in ref.authors)
    assert any(a.startswith("Jones") for a in ref.authors)


def test_extracts_doi_in_any_style() -> None:
    md = (
        "## References\n\n"
        "[1] Smith J. Title. Journal. 2023;1:1-2. doi:10.1038/s41586-024-08216-z\n"
        "[2] Jones K. Title. (2022). https://doi.org/10.1101/2022.01.01.476789\n"
    )
    refs = parse_references(md)
    assert refs[0].doi == "10.1038/s41586-024-08216-z"
    assert refs[1].doi == "10.1101/2022.01.01.476789"


def test_extracts_url_when_present() -> None:
    md = (
        "## References\n\n"
        "[1] Author. Online doc. https://example.com/paper.pdf\n"
    )
    refs = parse_references(md)
    assert refs[0].url == "https://example.com/paper.pdf"


def test_uses_last_references_heading_when_multiple() -> None:
    md = (
        "## Methods\n\n## References\n\n"
        "[1] Methods reference. 2010.\n\n"
        "## Discussion\n\nbody\n\n"
        "## References\n\n"
        "[1] Main reference. Journal. 2023;1:1.\n"
    )
    refs = parse_references(md)
    assert len(refs) == 1
    assert refs[0].raw.startswith("Main reference")


def test_handles_anchor_prefix_from_cross_reference_enhancer() -> None:
    md = (
        "## References\n\n"
        '<a id="ref-1"></a>[1] Smith J. Title. Journal. 2023;1:1.\n'
    )
    refs = parse_references(md)
    assert len(refs) == 1
    assert refs[0].id == "ref-1"
    assert refs[0].title == "Title"


def test_multi_line_entries_are_joined() -> None:
    md = (
        "## References\n\n"
        "[1] Smith J. Title that wraps onto\n"
        "    a second line. Journal. 2023;1:1-5.\n"
    )
    refs = parse_references(md)
    assert len(refs) == 1
    assert "wraps onto a second line" in refs[0].raw


def test_low_confidence_entry_keeps_raw() -> None:
    md = (
        "## References\n\n"
        "[1] partial garbled text without structure\n"
    )
    refs = parse_references(md)
    assert len(refs) == 1
    assert refs[0].raw.startswith("partial garbled text")
    assert refs[0].confidence < 0.5


def test_section_terminates_at_next_heading() -> None:
    md = (
        "## References\n\n"
        "[1] Smith J. Title. Journal. 2023;1:1.\n\n"
        "## Acknowledgements\n\n"
        "[2] not a reference, body of acknowledgements section.\n"
    )
    refs = parse_references(md)
    assert len(refs) == 1


def test_split_top_level_respects_parentheses() -> None:
    text = "Smith J (Brown lab). Title (revised). Journal. 2023;1:1."
    parts = _split_top_level(text, separator=". ")
    # The "(Brown lab)" parens should not interrupt the split, but the period
    # inside "(revised)" should not split either.
    assert parts[0] == "Smith J (Brown lab)"
    assert parts[1] == "Title (revised)"
    assert parts[2] == "Journal"


def test_internal_parsers_handle_minimal_input_gracefully() -> None:
    # Each internal parser must return a dict (possibly empty), never raise.
    assert _parse_vancouver("") == {}
    assert _parse_nature("") == {}
    assert _parse_apa("") == {}


def test_confidence_score_increases_with_field_coverage() -> None:
    md_minimal = "## References\n\n[1] something\n"
    md_full = (
        "## References\n\n"
        "[1] Smith J, Jones K. Real title. Journal. 2023;1:1-2. "
        "doi:10.1038/example\n"
    )
    minimal = parse_references(md_minimal)[0]
    full = parse_references(md_full)[0]
    assert full.confidence > minimal.confidence
    assert full.confidence >= 0.9


def test_implicit_block_detected_without_heading() -> None:
    """Nature/Science papers often omit a ``## References`` heading. The
    parser must still pick up the block when a long run of numbered entries
    sits at the end of the document."""
    md = "# Article body\n\nSome paragraph.\n\n" + "\n".join(
        f"{n}. Author{n} A. Title {n}. Journal. 2023;1:1-{n}."
        for n in range(1, 12)
    )
    refs = parse_references(md)
    assert len(refs) == 11
    assert refs[0].id == "ref-1"
    assert refs[-1].id == "ref-11"


def test_short_numbered_list_is_not_treated_as_bibliography() -> None:
    """A handful of numbered entries below the threshold must not be
    confused with a bibliography — those are usually ordered lists in the
    body of the paper."""
    md = "# Body\n\nSteps:\n\n1. First step\n2. Second step\n3. Third step\n"
    assert parse_references(md) == []


def test_inline_opener_splits_two_refs_on_one_line() -> None:
    """Two-column journal layouts can splice the left-column reference
    continuation with the right-column reference opener onto one physical
    line. The parser must recover both."""
    md = (
        "## References\n\n"
        "1. Smith, J. et al. Long title. Nature 567, 49–55 "
        "(2019). 27. Doe, J. & Roe, R. Other title. Cell 184, 810-826 (2021).\n"
    )
    refs = parse_references(md)
    ids = [r.id for r in refs]
    assert "ref-1" in ids
    assert "ref-27" in ids


def test_integration_nature_paper_yields_many_references() -> None:
    """End-to-end check on the converted Nature paper output. The bar is
    ``>= 30`` — the upstream extractor's column reflow is imperfect, so
    not every numbered entry in the source PDF survives reflow into a
    cleanly parseable shape. The realistic floor is well above 30."""
    import os
    md_path = "/tmp/bench-fast/nature-gut-adaptation.md"
    if not os.path.exists(md_path):
        import pytest
        pytest.skip(
            "/tmp/bench-fast/nature-gut-adaptation.md missing — run "
            "`uv run pdfvault benchmark --tier fast --output-dir /tmp/bench-fast`"
        )
    md = open(md_path).read()
    refs = parse_references(md)
    assert len(refs) >= 30
    assert sum(1 for r in refs if r.authors) >= 30


# --- Cell-press author-year style ---------------------------------------


def test_uppercase_references_heading_is_detected() -> None:
    """Cell, Trends, and many older Elsevier journals use ``## REFERENCES``
    (all caps). The locator regex is case-insensitive, but verifying the
    end-to-end path — heading + author-year body — guards against
    accidental tightening of the regex."""
    md = (
        "## REFERENCES\n\n"
        "Smith, J., Jones, K., and Lee, S. (2023). A title that survives. "
        "J. Cell Biol. 45, 100-110.\n"
        "Wong, A. and Chen, B. (2022). Another paper. Cell 184, 200-210.\n"
    )
    refs = parse_references(md)
    assert len(refs) == 2
    assert refs[0].year == "2023"
    assert refs[1].year == "2022"


def test_parses_cell_author_year_loose_format() -> None:
    """Cell entries with normal whitespace must parse all structural
    fields — the parser anchors on ``(YYYY)`` rather than relying on
    period-spacing being well-preserved."""
    md = (
        "## References\n\n"
        "Beltra, J.C., Bourbonnais, S., and Decaluwe, H. (2016). "
        "IL2Rb-dependent signals drive terminal exhaustion. "
        "Proc. Natl. Acad. Sci. USA 113, E5444-E5453.\n"
    )
    refs = parse_references(md)
    assert len(refs) == 1
    ref = refs[0]
    assert ref.year == "2016"
    assert ref.volume == "113"
    assert ref.pages == "E5444-E5453"
    assert "Beltra, J.C." in ref.authors
    assert "Bourbonnais, S." in ref.authors
    assert "Decaluwe, H." in ref.authors
    assert ref.confidence >= 0.7


def test_parses_cell_author_year_squished_format() -> None:
    """Cell-press exports lose inter-token whitespace when reflowing
    two-column layouts. The structural fields (authors, year, volume,
    pages) must still be recovered even when title and journal are run
    together."""
    md = (
        "## REFERENCES\n\n"
        "Anderson,K.G.,Mayer-Barber,K.,andMasopust,D.(2014)."
        "Intravascularstainingfordiscriminationoftissueleukocytes."
        "Nat.Protoc.9,209-222.\n"
    )
    refs = parse_references(md)
    assert len(refs) == 1
    ref = refs[0]
    assert ref.year == "2014"
    assert ref.volume == "9"
    assert ref.pages == "209-222"
    assert "Anderson, K.G." in ref.authors
    assert "Mayer-Barber, K." in ref.authors
    assert "Masopust, D." in ref.authors


def test_multi_line_author_block_does_not_split_into_two_entries() -> None:
    """A long Cell author list wraps onto a second physical line that
    also begins with ``Surname, X.``. Without the year-buffered guard,
    the splitter would treat the wrap as a brand-new entry. The
    implementation defers the new-entry decision until the previous
    entry has captured a ``(YYYY)`` marker."""
    md = (
        "## REFERENCES\n\n"
        "Alfei, F., Kanev, K., Hofmann, M., Wu, M., Ghoneim, H.E., Roelli, P.,\n"
        "Utzschneider, D.T., von Hoesslin, M., Cullen, J.G., Fan, Y., et al. "
        "(2019). TOX reinforces the phenotype of exhausted T cells. "
        "Nature 571, 265-269.\n"
        "Anderson, K.G. and Masopust, D. (2014). A different paper. "
        "Nat. Protoc. 9, 209-222.\n"
    )
    refs = parse_references(md)
    assert len(refs) == 2
    assert refs[0].year == "2019"
    assert refs[0].volume == "571"
    assert refs[1].year == "2014"
    assert "Alfei, F." in refs[0].authors
    # The wrapped second-line authors must end up in the FIRST entry,
    # not split off into a phantom entry.
    assert "Utzschneider, D.T." in refs[0].authors


def test_implicit_block_detected_for_author_year_run() -> None:
    """A long alphabetised author-year list with no ``## References``
    heading must still be picked up by the implicit-block detector.
    Cell-press and some older Elsevier exports omit the heading entirely
    when the references appear in a sidebar or boxed region."""
    surnames = [
        "Adams", "Brown", "Clark", "Davis", "Evans", "Foster",
        "Garcia", "Harris", "Irving", "Jones", "Klein",
    ]
    md = "# Body\n\nSome paragraph.\n\n" + "\n".join(
        f"{surname}, A. and Other, B. ({2020 + i % 5}). "
        f"Title {i + 1}. Journal {i + 1}, 1-{i + 1}."
        for i, surname in enumerate(surnames)
    )
    refs = parse_references(md)
    assert len(refs) == 11
    assert refs[0].year == "2020"
    assert refs[-1].id == "ref-11"


def test_existing_numbered_nature_entries_unaffected_by_cell_dispatch() -> None:
    """The Cell author-year dispatch must not steal Nature-style entries
    that share the ``Surname, X.`` opener — those entries end with
    ``(YYYY).`` and have a ``& Surname, Y.`` connector that the Cell
    detector excludes."""
    md = (
        "## References\n\n"
        "1. Smith, J. & Jones, K. Title of paper. J. Name 45, 100-110 (2023).\n"
    )
    refs = parse_references(md)
    assert len(refs) == 1
    ref = refs[0]
    assert ref.year == "2023"
    assert ref.volume == "45"
    assert ref.pages == "100-110"
    assert "Smith, J." in ref.authors
    assert "Jones, K." in ref.authors
    assert ref.confidence >= 0.7
