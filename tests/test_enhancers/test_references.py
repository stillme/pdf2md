"""Tests for the bibliography parser."""

from __future__ import annotations

from pdf2md.enhancers.references import (
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
            "`uv run pdf2md benchmark --tier fast --output-dir /tmp/bench-fast`"
        )
    md = open(md_path).read()
    refs = parse_references(md)
    assert len(refs) >= 30
    assert sum(1 for r in refs if r.authors) >= 30
