"""Tests for figure caption extraction and matching."""

from pdf2md.document import Figure
from pdf2md.enhancers.captions import (
    extract_figure_captions,
    extract_panel_references,
    insert_caption_text_blocks,
    match_captions_to_figures,
    remove_caption_text_blocks,
    sync_caption_alt_text,
)


def test_extract_nature_style_captions():
    text = "Fig. 1 | Mapping the spatial landscape of the intestine reveals regional and shared expression."
    captions = extract_figure_captions(text)
    assert len(captions) >= 1
    assert captions[0]["fig_num"] == 1
    assert "Mapping" in captions[0]["caption"]


def test_extract_standard_captions():
    text = "Figure 2. Results of the analysis showing significant differences."
    captions = extract_figure_captions(text)
    assert len(captions) >= 1
    assert captions[0]["fig_num"] == 2


def test_extract_colon_separator():
    text = "Fig. 5: Heatmap of gene expression across cell types."
    captions = extract_figure_captions(text)
    assert len(captions) >= 1
    assert captions[0]["fig_num"] == 5
    assert "Heatmap" in captions[0]["caption"]


def test_extract_extended_data():
    text = "Extended Data Fig. 3 | Additional validation experiments."
    captions = extract_figure_captions(text)
    assert len(captions) >= 1
    assert captions[0]["is_extended"] is True
    assert captions[0]["fig_num"] == 3


def test_extract_multiple_captions():
    text = (
        "Fig. 1 | First figure caption here.\n"
        "Some text in between.\n"
        "Fig. 2 | Second figure caption here."
    )
    captions = extract_figure_captions(text)
    assert len(captions) == 2
    assert captions[0]["fig_num"] == 1
    assert captions[1]["fig_num"] == 2


def test_extract_panel_references():
    text = "As shown in Fig. 3a, the results were consistent with Fig. 4c,d."
    refs = extract_panel_references(text)
    assert len(refs) >= 2
    assert refs[0]["fig_num"] == 3
    assert "a" in refs[0]["panels"]
    assert refs[1]["fig_num"] == 4


def test_extract_extended_data_panel_references():
    text = "The validation is shown in Extended Data Fig. 2a-c."
    refs = extract_panel_references(text)
    assert len(refs) == 1
    assert refs[0]["fig_num"] == 2
    assert refs[0]["is_extended"] is True
    assert set(refs[0]["panels"]) == {"a", "b", "c"}


def test_panel_range():
    text = "Fig. 2a\u2013c shows the progression."
    refs = extract_panel_references(text)
    assert len(refs) >= 1
    assert set(refs[0]["panels"]) == {"a", "b", "c"}


def test_panel_range_hyphen():
    text = "Fig. 7a-d displays the results."
    refs = extract_panel_references(text)
    assert len(refs) >= 1
    assert set(refs[0]["panels"]) == {"a", "b", "c", "d"}


def test_panel_context():
    text = "The data in Fig. 1a demonstrates the effect clearly."
    refs = extract_panel_references(text)
    assert len(refs) >= 1
    assert "demonstrates" in refs[0]["context"]


def test_no_captions_in_plain_text():
    text = "This is just regular text without any figure references."
    captions = extract_figure_captions(text)
    assert len(captions) == 0


def test_no_panel_refs_in_plain_text():
    text = "This is just regular text without any figure references."
    refs = extract_panel_references(text)
    assert len(refs) == 0


def test_match_captions_to_figures():
    figures = [
        Figure(id="fig1", page=0),
        Figure(id="fig2", page=1),
        Figure(id="fig3", page=2),
    ]
    captions = [
        {"fig_num": 1, "caption": "First caption.", "is_extended": False},
        {"fig_num": 2, "caption": "Second caption.", "is_extended": False},
    ]
    result = match_captions_to_figures(figures, captions)
    assert result[0].caption == "First caption."
    assert result[1].caption == "Second caption."
    assert result[2].caption is None  # no caption for fig3


def test_match_uses_page_order_and_replaces_next_page_placeholders():
    figures = [
        Figure(id="fig1", page=1, image_base64="small"),
        Figure(id="fig2", page=2, image_base64="small"),
        Figure(id="fig3", page=10, image_base64="large" * 100),
        Figure(id="fig4", page=11, image_base64="large" * 100),
    ]
    captions = [
        {"fig_num": 1, "caption": "Main one.", "is_extended": False},
        {"fig_num": 2, "caption": "Main two.", "is_extended": False},
        {"fig_num": 1, "caption": "See next page for caption.", "is_extended": True},
        {"fig_num": 1, "caption": "Extended one.", "is_extended": True},
        {"fig_num": 2, "caption": "See next page for caption.", "is_extended": True},
        {"fig_num": 2, "caption": "Extended two.", "is_extended": True},
    ]

    result = match_captions_to_figures(figures, captions)

    assert [f.caption for f in result] == [
        "Main one.",
        "Main two.",
        "Extended one.",
        "Extended two.",
    ]


def test_sync_caption_alt_text_includes_figure_labels():
    figures = [
        Figure(id="fig1", page=1),
        Figure(id="fig2", page=10),
    ]
    captions = [
        {"fig_num": 1, "caption": "Main caption.", "is_extended": False},
        {"fig_num": 1, "caption": "Extended caption.", "is_extended": True},
    ]
    markdown = "![Figure 1](fig1)\n\n![Figure 2](fig2)"

    result = sync_caption_alt_text(markdown, figures, captions)

    assert "![Fig. 1 | Main caption.](fig1)" in result
    assert "![Extended Data Fig. 1 | Extended caption.](fig2)" in result


def test_remove_caption_text_blocks_uses_extracted_line_range():
    markdown = (
        "Body before\n"
        "Fig. 1 | Full caption title.\n"
        "a, Panel text.\n"
        "\n"
        "Body after"
    )
    captions = extract_figure_captions(markdown)

    result = remove_caption_text_blocks(markdown, captions)

    assert "Fig. 1 |" not in result
    assert "a, Panel text." not in result
    assert "Body before" in result
    assert "Body after" in result


def test_insert_caption_text_blocks_uses_full_caption_after_marker():
    figures = [Figure(id="fig1", page=1)]
    captions = [
        {
            "fig_num": 1,
            "caption": (
                "Main title. a, Panel text. Processed using ImageJ and "
                "representative of n = 5 biological replicates. Scale bar, 1,000 um."
            ),
            "is_extended": False,
        },
    ]
    markdown = "![Figure 1](fig1)"

    result = insert_caption_text_blocks(markdown, figures, captions)

    assert "![Figure 1](fig1)" in result
    assert "Fig. 1 | Main title. a, Panel text." in result
    assert "Processed using ImageJ" in result
    assert "Scale bar, 1,000 um." in result


def test_insert_caption_text_blocks_moves_sentence_interruptions():
    figures = [Figure(id="fig1", page=1)]
    captions = [{"fig_num": 1, "caption": "Main title. a, Panel text.", "is_extended": False}]
    markdown = (
        "To understand transcriptional\n"
        "![Figure 1](fig1)\n"
        "signatures, we mapped TFs.\n"
        "\n"
        "Next paragraph."
    )

    result = insert_caption_text_blocks(markdown, figures, captions)

    assert "transcriptional\nsignatures" in result
    assert "signatures, we mapped TFs.\n\n![Figure 1](fig1)" in result


def test_insert_caption_text_blocks_moves_adjacent_sentence_interruptions():
    figures = [Figure(id="fig3", page=3), Figure(id="fig4", page=4)]
    captions = [
        {"fig_num": 3, "caption": "Third title. a, Panel text.", "is_extended": False},
        {"fig_num": 4, "caption": "Fourth title. a, Panel text.", "is_extended": False},
    ]
    markdown = (
        "We identified\n"
        "![Figure 3](fig3)\n"
        "![Figure 4](fig4)\n"
        "subsets of each lineage.\n\n"
        "Next paragraph."
    )

    result = insert_caption_text_blocks(markdown, figures, captions)

    assert "We identified\nsubsets of each lineage." in result
    assert "subsets of each lineage.\n\n![Figure 3](fig3)" in result
    assert result.index("![Figure 3](fig3)") < result.index("![Figure 4](fig4)")
    assert "Fig. 3 | Third title." in result
    assert "Fig. 4 | Fourth title." in result


def test_insert_caption_text_blocks_rechecks_cascaded_interruptions():
    figures = [Figure(id="fig3", page=3), Figure(id="fig4", page=4)]
    captions = [
        {"fig_num": 3, "caption": "Third title. a, Panel text.", "is_extended": False},
        {"fig_num": 4, "caption": "Fourth title. a, Panel text.", "is_extended": False},
    ]
    markdown = (
        "distribution of cell types and identified\n"
        "![Figure 3](fig3)\n"
        "differential enrichment across this axis.\n"
        "We identified\n"
        "![Figure 4](fig4)\n"
        "subsets of each lineage.\n\n"
        "Next paragraph."
    )

    result = insert_caption_text_blocks(markdown, figures, captions)

    assert "identified\ndifferential enrichment across this axis." in result
    assert "We identified\nsubsets of each lineage." in result
    assert "differential enrichment across this axis.\n\n![Figure 3](fig3)" in result
    assert "subsets of each lineage.\n\n![Figure 4](fig4)" in result
    assert result.index("![Figure 3](fig3)") < result.index("![Figure 4](fig4)")


def test_match_skips_already_captioned():
    figures = [
        Figure(id="fig1", caption="Existing caption", page=0),
        Figure(id="fig2", page=1),
    ]
    captions = [
        {"fig_num": 1, "caption": "New caption.", "is_extended": False},
    ]
    result = match_captions_to_figures(figures, captions)
    # fig1 already had a caption, so the new one goes to fig2
    assert result[0].caption == "Existing caption"
    assert result[1].caption == "New caption."


def test_match_empty_figures():
    result = match_captions_to_figures([], [{"fig_num": 1, "caption": "Test.", "is_extended": False}])
    assert result == []


def test_match_empty_captions():
    figures = [Figure(id="fig1", page=0)]
    result = match_captions_to_figures(figures, [])
    assert result[0].caption is None
