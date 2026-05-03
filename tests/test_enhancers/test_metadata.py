"""Tests for metadata enhancer."""
from pdfvault.enhancers.metadata import extract_metadata


def test_extract_title_from_text():
    text = "Sample Research Paper\n\nJohn Smith, Jane Doe\n\nAbstract\nThis paper..."
    meta = extract_metadata(text, pages=2)
    assert meta.title == "Sample Research Paper"
    assert meta.pages == 2


def test_extract_authors():
    text = "My Title\n\nAlice Johnson, Bob Williams, Carol Chen\n\nIntroduction\nSome text."
    meta = extract_metadata(text, pages=1)
    assert len(meta.authors) >= 2


def test_extract_doi():
    text = "Title\n\nDOI: 10.1234/example.2024.001\n\nAbstract"
    meta = extract_metadata(text, pages=1)
    assert meta.doi == "10.1234/example.2024.001"


def test_no_metadata():
    text = "Just some random text without structure."
    meta = extract_metadata(text, pages=1)
    assert meta.pages == 1


def test_extract_short_title():
    text = "Mistral 7B\nAlbert Q. Jiang, Alexandre Sablayrolles\n\nAbstract\nWe introduce..."
    meta = extract_metadata(text, pages=9)
    assert meta.title == "Mistral 7B"


def test_extract_title_skips_license():
    text = "Permission is hereby granted, free of charge\nAttention Is All You Need\nAuthors\n\nAbstract"
    meta = extract_metadata(text, pages=15)
    assert "Attention" in meta.title
    assert "permission" not in meta.title.lower()


def test_extract_title_skips_affiliations():
    text = "Department of Computer Science, MIT\nMy Great Paper Title\nJohn Smith\n\nAbstract"
    meta = extract_metadata(text, pages=5)
    assert meta.title == "My Great Paper Title"


def test_extract_title_skips_journal_header():
    text = "Nature | Vol 636 | 12 December 2024 | 447\nArticle\nSpatially restricted immune and microbiota-driven adaptation of the gut\nToufic Mayassi, Chenhao Li\n\nAbstract"
    meta = extract_metadata(text, pages=41)
    assert "Spatially restricted" in meta.title
    assert "Nature" not in meta.title


def test_extract_title_skips_review_article_badge():
    """Nature-Reviews-style header bands often have ``Review article``
    and ``Check for updates`` as side-by-side badges that get extracted
    as a single line. Both must be filtered so the actual paper title
    on the next non-empty line is picked up."""
    text = (
        "Nature Reviews Genetics | Volume 27 | March 2026\n"
        "https://doi.org/10.1038/s41576-025-00907-1\n"
        "Review article                        Check for updates\n"
        "Harnessing artificial intelligence to advance CRISPR-based\n"
        "Tyler Thomson, Gen Li, Amy Strilchuk\n"
        "\n"
        "Abstract\nText..."
    )
    meta = extract_metadata(text, pages=19)
    assert "Harnessing" in (meta.title or ""), f"got title={meta.title!r}"
    assert "Review article" not in (meta.title or "")
    assert "Check for updates" not in (meta.title or "")


def test_extract_title_joins_multiline_fragments():
    """layout=True extraction can split a single title across 2-3
    short lines with whitespace gaps. The extractor must rejoin the
    fragments into one title string."""
    text = (
        "Harnessing artificial intelligence\n"
        "\n"
        "to advance CRISPR-based\n"
        "\n"
        "genome editing technologies\n"
        "\n"
        "Tyler Thomson, Gen Li, Amy Strilchuk\n"
        "\n"
        "Abstract\nText..."
    )
    meta = extract_metadata(text, pages=19)
    title = meta.title or ""
    assert "Harnessing artificial intelligence" in title
    assert "CRISPR-based" in title
    assert "genome editing technologies" in title


def test_extract_title_does_not_swallow_author_line():
    """A single ``First Last`` line right after the title is the start
    of the author block — must not be glued onto the title."""
    text = (
        "Sample Research Paper\n"
        "John Smith\n"
        "\n"
        "Abstract\nText..."
    )
    meta = extract_metadata(text, pages=2)
    assert meta.title == "Sample Research Paper"


def test_extract_title_stops_at_terminal_punctuation():
    """A line ending with a sentence terminator can't be a title
    continuation — the title is whatever came before."""
    text = (
        "Real Title Here\n"
        "This is a complete sentence and not a title fragment.\n"
        "Authors Go Here\n"
        "\n"
        "Abstract"
    )
    meta = extract_metadata(text, pages=3)
    assert meta.title == "Real Title Here"


def test_extract_title_skips_brief_communication_badge():
    text = (
        "Brief Communication\n"
        "A Concise Study of Something Important\n"
        "Author Names Here, Other Author\n"
        "\n"
        "Abstract"
    )
    meta = extract_metadata(text, pages=4)
    assert meta.title == "A Concise Study of Something Important"
