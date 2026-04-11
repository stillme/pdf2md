"""Tests for lightweight figure index sidecars."""

import base64
import hashlib

from pdf2md.document import Figure
from pdf2md.enhancers.figure_index import build_figure_index


def test_build_figure_index_maps_caption_blocks_and_mentions():
    image_bytes = b"fake-png"
    figures = [
        Figure(
            id="fig1",
            page=1,
            caption="Mapping title. a, First panel. b, Second panel.",
            image_base64=base64.b64encode(image_bytes).decode(),
        ),
        Figure(
            id="fig2",
            page=10,
            caption="Extended validation. a, Validation panel.",
        ),
    ]
    markdown = (
        "The results are shown in Fig. 1a,b and Extended Data Fig. 1a.\n\n"
        "![Fig. 1 | Mapping title.](fig1)\n\n"
        "Fig. 1 | Mapping title. a, First panel. b, Second panel.\n\n"
        "![Extended Data Fig. 1 | Extended validation.](fig2)\n\n"
        "Extended Data Fig. 1 | Extended validation. a, Validation panel."
    )

    index = build_figure_index(markdown, figures)

    assert len(index) == 2
    assert index[0].figure_id == "fig1"
    assert index[0].label == "Fig. 1"
    assert index[0].figure_number == 1
    assert index[0].caption.startswith("Mapping title")
    assert index[0].panels == ["a", "b"]
    assert len(index[0].mentions) == 1
    assert index[0].image_hash == "sha256:" + hashlib.sha256(image_bytes).hexdigest()
    assert index[1].figure_id == "fig2"
    assert index[1].label == "Extended Data Fig. 1"
    assert index[1].is_extended is True
    assert index[1].panels == ["a"]
    assert len(index[1].mentions) == 1


def test_build_figure_index_handles_unlabeled_figures():
    figures = [Figure(id="fig3", page=2)]
    index = build_figure_index("![Figure 3](fig3)", figures)

    assert index[0].figure_id == "fig3"
    assert index[0].label == "Figure 3"
    assert index[0].figure_number == 3
    assert index[0].caption is None
    assert index[0].parse_confidence == 0.5


def test_build_figure_index_ignores_caption_text_mentions():
    figures = [
        Figure(
            id="fig1",
            page=1,
            caption="Figure with a cross reference to Fig. 1a.",
        ),
    ]
    markdown = (
        "![Fig. 1 | Figure with a cross reference.](fig1)\n\n"
        "Fig. 1 | Figure with a cross reference to Fig. 1a.\n\n"
        "Body text without panel references."
    )

    index = build_figure_index(markdown, figures)

    assert index[0].mentions == []
