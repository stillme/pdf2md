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


# --- Annotation block detection ---

def test_removes_long_annotation_block():
    """Blocks of metabolite/pathway names (>15 chars each) should be removed.

    Requires 6+ lines with no strong sentence structure AND at least one short line.
    """
    text = (
        "We examined the transcriptional landscape.\n"
        "Short chain fatty acids Bile acids\n"
        "Adenosine triphosphate\n"
        "Adenosine diphosphate\n"
        "Creatine Glycine\n"
        "Beta-alanine Proline\n"
        "Beta-lactam antibiotics\n"
        "Antifolates\n"
        "The data demonstrate significant effects."
    )
    cleaned = clean_figure_text(text)
    assert "Short chain fatty acids" not in cleaned
    assert "Adenosine triphosphate" not in cleaned
    assert "Beta-alanine Proline" not in cleaned
    assert "Antifolates" not in cleaned
    assert "We examined" in cleaned
    assert "data demonstrate" in cleaned


def test_removes_annotation_block_with_single_sentence_words():
    """Blocks with single sentence words like 'and' in 'Di- and tri-peptides' should still be caught."""
    text = (
        "Expression patterns shown in figure.\n"
        "Inorganic phosphate\n"
        "Oxalate Glucose Fructose\n"
        "Ferrous iron Folates\n"
        "Protons Di- and tri-peptides\n"
        "Beta-alanine Proline\n"
        "Antifolates\n"
        "The results were significant and reproducible."
    )
    cleaned = clean_figure_text(text)
    assert "Inorganic phosphate" not in cleaned
    assert "Ferrous iron" not in cleaned
    assert "Antifolates" not in cleaned
    assert "Expression patterns" in cleaned
    assert "results were significant" in cleaned


def test_preserves_short_non_sentence_blocks():
    """3-4 non-sentence lines without short ratio shouldn't be falsely removed."""
    text = (
        "Introduction to the study.\n"
        "Spatial transcriptomics\n"
        "Foundation models\n"
        "Perturbation prediction\n"
        "These methods were combined in our analysis."
    )
    cleaned = clean_figure_text(text)
    # Only 3 non-sentence lines — below the 5-line annotation threshold,
    # and short_ratio is not >0.6, so they should be preserved
    assert "Spatial transcriptomics" in cleaned
    assert "Foundation models" in cleaned


def test_removes_isolated_figure_title_between_sentence_fragments():
    text = (
        "regions of tissue were associated with a unique transcriptional program,\n"
        "Upregulated genes in the middle colon\n"
        "\n"
        "we compared high- with low-expressing regions of Ido1."
    )

    cleaned = clean_figure_text(text)

    assert "Upregulated genes in the middle colon" not in cleaned
    assert "unique transcriptional program" in cleaned
    assert "we compared high" in cleaned


def test_preserves_image_marker_between_sentence_fragments():
    text = (
        "regions of tissue were associated with a unique transcriptional program,\n"
        "![Figure 2](fig2)\n"
        "\n"
        "we compared high- with low-expressing regions of Ido1."
    )

    cleaned = clean_figure_text(text)

    assert "![Figure 2](fig2)" in cleaned
    assert "we compared high" in cleaned


def test_removes_cell_state_axis_label_block():
    text = (
        "We identified the adapted subset in the middle colon.\n"
        "in prevalence log2FC in prevalence\n"
        "A B C D A B C D A B C D\n"
        "Percentage of cells\n"
        "Stem/TA cells Immature enterocytes I Immature enterocytes II Mature enterocytes I\n"
        "SPF GF FMT\n"
        "A B C D A B C D A B C D\n"
        "Ccn3-hi GCs Reg4+ GCs I Reg4+ GCs II\n"
        "The next body sentence remains."
    )

    cleaned = clean_figure_text(text)

    assert "in prevalence log2FC" not in cleaned
    assert "Percentage of cells" not in cleaned
    assert "SPF GF FMT" not in cleaned
    assert "Ccn3-hi GCs" not in cleaned
    assert "We identified the adapted subset" in cleaned
    assert "The next body sentence remains." in cleaned


def test_removes_single_cell_state_axis_label_line():
    text = (
        "Our spatial mapping results matched expected spatial assignment.\n"
        "Stem/TA cells Immature enterocytes I Immature enterocytes II Mature enterocytes I Mature enterocytes II\n"
        "subsets of each lineage were differentially enriched."
    )

    cleaned = clean_figure_text(text)

    assert "Stem/TA cells" not in cleaned
    assert "Our spatial mapping results" in cleaned
    assert "subsets of each lineage" in cleaned


def test_preserves_author_blocks():
    """Author name blocks with affiliations should NOT be removed."""
    text = (
        "Title of the paper.\n"
        "Toufic Mayassi1,2,9, Chenhao Li1,2,3,9\n"
        ", Eric M. Brown1,2,3, Rebecca Weisberg1,2\n"
        "Toru Nakata2,3,4, Hiroshi Yano5,6,7\n"
        ", David Artis5,6,7,8, Daniel B. Graham1,2,3\n"
        "Ramnik J. Xavier1,2,3,4\n"
        "The intestine is characterized by an environment."
    )
    cleaned = clean_figure_text(text)
    assert "Mayassi" in cleaned
    assert "Brown" in cleaned
    assert "Xavier" in cleaned


def test_preserves_real_prose_with_mixed_sentence_words():
    """Real sentences should never be removed, even short ones."""
    text = (
        "We found the spatial landscape was robust.\n"
        "The microbiota had a major impact.\n"
        "These genes were highly expressed.\n"
        "The results were confirmed by qPCR.\n"
        "We next examined the colon tissue.\n"
        "The data support our hypothesis."
    )
    cleaned = clean_figure_text(text)
    # All lines have 2+ sentence words — nothing should be removed
    assert text == cleaned


def test_removes_next_page_caption_placeholders():
    text = (
        "Body text before.\n"
        "Extended Data Fig. 1 | See next page for caption.\n"
        "![Figure 6](fig6)\n"
        "Body text after."
    )

    cleaned = clean_figure_text(text)

    assert "See next page for caption" not in cleaned
    assert "![Figure 6](fig6)" in cleaned
    assert "Body text before" in cleaned
    assert "Body text after" in cleaned


def test_removes_legend_statistical_sentences():
    text = (
        "Fig. 2 | Example caption. Processed using ImageJ and representative of "
        "n = 5 biological replicates. Scale bar, 1,000 um.\n"
        "The next body sentence remains."
    )

    cleaned = clean_figure_text(text)

    assert "Processed using ImageJ" not in cleaned
    assert "biological replicates" not in cleaned
    assert "Scale bar" not in cleaned
    assert "Fig. 2 | Example caption." in cleaned
    assert "The next body sentence remains." in cleaned


def test_removes_legend_statistical_parentheticals():
    text = (
        "Fig. 10 | Caption title. Boxplots showing the fraction of each cluster "
        "(3 biological replicates per box). Expression of marker genes follows."
    )

    cleaned = clean_figure_text(text)

    assert "biological replicates" not in cleaned
    assert "Boxplots showing the fraction" in cleaned
    assert "Expression of marker genes follows" in cleaned
