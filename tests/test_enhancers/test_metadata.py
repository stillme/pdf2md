"""Tests for metadata enhancer."""
from pdf2md.enhancers.metadata import extract_metadata


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
