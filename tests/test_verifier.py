"""Tests for the agentic verify-correct loop."""
from unittest.mock import MagicMock
import json

from pdf2md.providers.base import VerifyCorrection, VerifyResult
from pdf2md.verifier import (
    _apply_corrections,
    run_verify_loop,
    verify_page,
)


# ---------------------------------------------------------------------------
# verify_page / parser tests (legacy coverage, updated for new schema)
# ---------------------------------------------------------------------------

def test_verify_pass():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = json.dumps({
        "status": "pass", "confidence": 0.95, "corrections": [],
    })
    result = verify_page(
        page_image=b"fake_image",
        extracted_markdown="# Introduction\n\nSome text.",
        provider=mock_provider,
    )
    assert result.status == "pass"
    assert result.confidence >= 0.9


def test_verify_fail_with_corrections():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = json.dumps({
        "status": "fail",
        "confidence": 0.4,
        "corrections": [
            {
                "region": "paragraph2",
                "before_context": "before ",
                "after_context": " after",
                "original": "wrong text",
                "replacement": "right text",
            },
        ],
    })
    result = verify_page(
        page_image=b"fake_image",
        extracted_markdown="# Results\n\nIncomplete text.",
        provider=mock_provider,
    )
    assert result.status == "fail"
    assert len(result.corrections) == 1
    assert isinstance(result.corrections[0], VerifyCorrection)
    assert result.corrections[0].original == "wrong text"


def test_verify_handles_non_json_response():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = "This looks correct to me."
    result = verify_page(
        page_image=b"fake_image",
        extracted_markdown="Some text.",
        provider=mock_provider,
    )
    assert result.status == "pass"
    assert result.confidence >= 0.5


def test_verify_page_returns_error_on_provider_exception():
    mock_provider = MagicMock()
    mock_provider.complete_sync.side_effect = Exception("API error")
    result = verify_page(page_image=b"fake_image", extracted_markdown="Some text.", provider=mock_provider)
    assert result.status == "error"
    assert result.confidence == 0.0
    assert result.corrections == []
    assert "API error" in result.explanation


def test_run_verify_loop_does_not_loop_on_error():
    mock_provider = MagicMock()
    mock_provider.complete_sync.side_effect = Exception("network down")
    original = "Some original markdown."
    markdown, confidence = run_verify_loop(b"fake_image", original, mock_provider, max_rounds=3)
    assert markdown == original
    assert confidence == 0.0
    assert mock_provider.complete_sync.call_count == 1


def test_verify_loop_passes_immediately():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = json.dumps({
        "status": "pass", "confidence": 0.95, "corrections": [],
    })
    markdown, confidence = run_verify_loop(
        b"fake_image", "Good markdown.", mock_provider, max_rounds=2,
    )
    assert confidence >= 0.9
    assert markdown == "Good markdown."
    assert mock_provider.complete_sync.call_count == 1


def test_verify_loop_corrects_and_re_verifies():
    mock_provider = MagicMock()
    responses = [
        json.dumps({
            "status": "fail",
            "confidence": 0.4,
            "corrections": [
                {
                    "region": "p1",
                    "before_context": "Some text with ",
                    "after_context": ".",
                    "original": "typo",
                    "replacement": "fixed",
                },
            ],
        }),
        json.dumps({"status": "pass", "confidence": 0.9, "corrections": []}),
    ]
    mock_provider.complete_sync.side_effect = responses
    markdown, confidence = run_verify_loop(
        b"fake_image",
        "Some text with typo.",
        mock_provider,
        max_rounds=2,
    )
    assert confidence >= 0.4
    assert "fixed" in markdown
    assert mock_provider.complete_sync.call_count == 2


# ---------------------------------------------------------------------------
# _apply_corrections tests
# ---------------------------------------------------------------------------

def test_apply_corrections_unique_match():
    """Single, unambiguous correction is applied verbatim."""
    md = "The quick brown fox jumps over the lazy dog."
    correction = VerifyCorrection(
        region="sentence",
        before_context="The quick ",
        after_context=" fox",
        original="brown",
        replacement="red",
    )
    corrected, summary = _apply_corrections(md, [correction])
    assert corrected == "The quick red fox jumps over the lazy dog."
    assert summary.applied == 1
    assert summary.skipped_no_match == 0
    assert summary.skipped_ambiguous == 0


def test_apply_corrections_no_match():
    """When ``original`` is not in the markdown, skip without changing it."""
    md = "Hello world."
    correction = VerifyCorrection(
        before_context="",
        after_context="",
        original="missing phrase",
        replacement="new phrase",
    )
    corrected, summary = _apply_corrections(md, [correction])
    assert corrected == md
    assert summary.applied == 0
    assert summary.skipped_no_match == 1
    assert summary.skipped_ambiguous == 0


def test_apply_corrections_ambiguous():
    """Ambiguous patches are skipped; contexts disambiguate when provided."""
    md = "See Fig. 1 for details. Fig. 1 shows X. In Fig. 1 we plot Y."

    # Without context, "Fig. 1" appears 3 times → skipped as ambiguous.
    no_ctx = VerifyCorrection(
        before_context="",
        after_context="",
        original="Fig. 1",
        replacement="Fig. 2",
    )
    corrected, summary = _apply_corrections(md, [no_ctx])
    assert corrected == md
    assert summary.applied == 0
    assert summary.skipped_ambiguous == 1
    assert summary.skipped_no_match == 0

    # With unique context, the correct instance is replaced.
    with_ctx = VerifyCorrection(
        before_context="See ",
        after_context=" for details.",
        original="Fig. 1",
        replacement="Fig. 2",
    )
    corrected2, summary2 = _apply_corrections(md, [with_ctx])
    assert corrected2 == (
        "See Fig. 2 for details. Fig. 1 shows X. In Fig. 1 we plot Y."
    )
    assert summary2.applied == 1
    assert summary2.skipped_ambiguous == 0
    assert summary2.skipped_no_match == 0


def test_apply_corrections_legacy_shape():
    """Old ``{problem, fix}`` shape is converted and applied if unambiguous."""
    md = "Hello world."
    legacy = {"region": "greeting", "problem": "world", "fix": "there"}
    corrected, summary = _apply_corrections(md, [legacy])
    assert corrected == "Hello there."
    assert summary.applied == 1
    assert summary.skipped_no_match == 0
    assert summary.skipped_ambiguous == 0


def test_run_verify_loop_records_skipped():
    """Mocked VLM returns one applicable, one no-match, and one ambiguous
    correction. The patch-summary callback should observe the right counts."""
    md = "Cats and dogs. Cats and dogs. The hen clucks."
    corrections = [
        # Applies — unique location for "hen" -> "rooster".
        {
            "region": "animal",
            "before_context": "The ",
            "after_context": " clucks.",
            "original": "hen",
            "replacement": "rooster",
        },
        # No match — original text is not present.
        {
            "region": "missing",
            "before_context": "",
            "after_context": "",
            "original": "wolves",
            "replacement": "foxes",
        },
        # Ambiguous — "Cats and dogs" appears twice without context.
        {
            "region": "ambiguous",
            "before_context": "",
            "after_context": "",
            "original": "Cats and dogs",
            "replacement": "Birds and bees",
        },
    ]

    mock_provider = MagicMock()
    mock_provider.complete_sync.side_effect = [
        json.dumps({
            "status": "fail",
            "confidence": 0.4,
            "corrections": corrections,
        }),
        json.dumps({"status": "pass", "confidence": 0.9, "corrections": []}),
    ]

    observed = []
    markdown, confidence = run_verify_loop(
        b"fake_image",
        md,
        mock_provider,
        max_rounds=2,
        on_patch_summary=observed.append,
    )

    # The applicable correction was applied; the others left the markdown
    # unchanged.
    assert "rooster" in markdown
    assert markdown.count("Cats and dogs") == 2
    assert "wolves" not in markdown

    # Return type contract: still a 2-tuple of (str, float).
    assert isinstance(markdown, str)
    assert isinstance(confidence, float)

    assert len(observed) == 1
    summary = observed[0]
    assert summary.applied == 1
    assert summary.skipped_no_match == 1
    assert summary.skipped_ambiguous == 1

    # The summary string a caller would log / surface to ``doc.warnings``.
    expected = (
        "verify page 1: 1 applied, 1 no-match, 1 ambiguous"
    )
    rendered = (
        f"verify page 1: {summary.applied} applied, "
        f"{summary.skipped_no_match} no-match, "
        f"{summary.skipped_ambiguous} ambiguous"
    )
    assert rendered == expected


# ---------------------------------------------------------------------------
# VerifyResult parsing — make sure legacy {problem, fix} payloads still parse
# ---------------------------------------------------------------------------

def test_verify_result_parses_legacy_corrections():
    """A VLM that still emits ``{problem, fix}`` should not blow up parsing.

    The legacy payload is converted into VerifyCorrection with empty contexts
    (so ``_apply_corrections`` will only apply when the text is unambiguous)."""
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = json.dumps({
        "status": "fail",
        "confidence": 0.4,
        "corrections": [
            {"region": "p1", "problem": "typo", "fix": "fixed"},
        ],
    })
    result = verify_page(
        page_image=b"fake_image",
        extracted_markdown="Some text.",
        provider=mock_provider,
    )
    assert isinstance(result, VerifyResult)
    assert len(result.corrections) == 1
    c = result.corrections[0]
    assert isinstance(c, VerifyCorrection)
    assert c.original == "typo"
    assert c.replacement == "fixed"
    assert c.before_context == ""
    assert c.after_context == ""
