"""Tests for figure text leak cleaner."""

from pdf2md.enhancers.text_cleaner import clean_figure_text


def test_removes_gene_name_blocks():
    """Blocks of gene names (3+ consecutive short lines) should be removed."""
    text = "Real sentence here.\nSpink4 Phgr1\nSlc51a\nS100a6\nGuca2a\nAnother real sentence."
    cleaned = clean_figure_text(text)
    assert "Spink4" not in cleaned
    assert "Real sentence" in cleaned
    assert "Another real" in cleaned


def test_removes_axis_labels():
    """Blocks of numeric axis tick labels should be removed."""
    text = "Results shown below.\n0.5\n1.0\n1.5\n2.0\nThe data demonstrate significant effects."
    cleaned = clean_figure_text(text)
    assert "0.5" not in cleaned
    assert "Results" in cleaned
    assert "data demonstrate" in cleaned


def test_removes_cluster_labels():
    """Blocks of cluster labels like C1, C2, C3 should be removed."""
    text = "The clustering analysis.\nC1\nC2\nC3\nThree clusters were identified in the data."
    cleaned = clean_figure_text(text)
    assert "C1" not in cleaned
    assert "clustering analysis" in cleaned
    assert "Three clusters" in cleaned


def test_preserves_real_content():
    """Full sentences mentioning gene names should NOT be stripped."""
    text = "The gene Spink4 was highly expressed in the epithelium."
    cleaned = clean_figure_text(text)
    assert text == cleaned


def test_preserves_short_real_content():
    """Short but meaningful lines should not be stripped."""
    text = "Introduction\nThis is the abstract.\nResults\nWe found significant effects."
    cleaned = clean_figure_text(text)
    assert "Introduction" in cleaned
    assert "Results" in cleaned


def test_removes_mixed_gene_number_block():
    """Blocks mixing gene names and numbers (typical figure legend) should be removed."""
    text = (
        "Expression patterns shown in figure.\n"
        "Reg3b\n"
        "Ang4\n"
        "Defa21\n"
        "Defa22\n"
        "Tmigd1\n"
        "This demonstrates regional expression differences."
    )
    cleaned = clean_figure_text(text)
    assert "Reg3b" not in cleaned
    assert "Ang4" not in cleaned
    assert "Expression patterns" in cleaned
    assert "demonstrates" in cleaned


def test_preserves_paragraph_with_short_words():
    """Normal paragraphs with a few short words should be preserved."""
    text = "We observed that in the SI and colon regions there were distinct patterns."
    cleaned = clean_figure_text(text)
    assert text == cleaned


def test_does_not_strip_real_numbered_content():
    """Real content that happens to contain numbers should be preserved."""
    text = "The sample contained 2,453 genes with differential enrichment across 7 regions."
    cleaned = clean_figure_text(text)
    assert text == cleaned


def test_empty_text():
    """Empty text should return empty."""
    assert clean_figure_text("") == ""


def test_single_line_text():
    """A single valid sentence should be preserved."""
    text = "The intestine is characterized by an environment."
    cleaned = clean_figure_text(text)
    assert text == cleaned
