"""Tests for the Nature quality benchmark scorer."""

from autoresearch.scorer import (
    score_body_coherence,
    score_completeness,
    score_legend_separation,
    score_superscript_precision,
)


def test_completeness_uses_phrase_present_in_pdf_text():
    md = (
        "spatial transcriptome murine intestine Visium circadian rhythm "
        "goblet cells enterocytes fibroblasts Crohn ulcerative colitis "
        "spatially restricted faecal microbiota transplant "
        "Patches and immune follicles"
    )

    assert score_completeness(md) == 1.0


def test_superscript_precision_does_not_count_valid_author_affiliations():
    md = (
        "Mayassi<sup>1,2,9</sup> Li<sup>1,2,3,9</sup> "
        "Xavier<sup>1,2,3,4</sup> regions<sup>1-8</sup> "
        "GCs<sup>32,33</sup>"
    )

    assert score_superscript_precision(md) == 1.0


def test_superscript_precision_still_counts_gene_name_false_positive():
    md = (
        "Mayassi<sup>1,2,9</sup> Li<sup>1,2,3,9</sup> "
        "Xavier<sup>1,2,3,4</sup> regions<sup>1-8</sup> "
        "Ang<sup>4</sup>"
    )

    assert score_superscript_precision(md) < 1.0


def test_legend_separation_allows_text_inside_caption_blocks():
    md = (
        "Body prose.\n\n"
        "![Fig. 2 | Spatial transcriptomics reveals a microbiota-driven adaptation.](fig2)\n\n"
        "Fig. 2 | Spatial transcriptomics reveals a microbiota-driven adaptation. "
        "Processed using ImageJ and representative of n = 5 biological replicates. "
        "Scale bar, 1,000 um.\n\n"
        "More body prose."
    )

    assert score_legend_separation(md) == 1.0


def test_body_coherence_allows_caption_block_after_image_marker():
    md = (
        "Complete body sentence.\n\n"
        "![Fig. 1 | Caption title.](fig1)\n\n"
        "Fig. 1 | Caption title. a, Panel text.\n\n"
        "Another complete body sentence."
    )

    assert score_body_coherence(md) == 1.0
