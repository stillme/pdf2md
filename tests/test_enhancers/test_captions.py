"""Tests for figure caption extraction and matching."""

from pdf2md.document import Figure
from pdf2md.enhancers.captions import (
    extract_figure_captions,
    extract_panel_references,
    match_captions_to_figures,
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
