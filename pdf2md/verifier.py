"""Agentic verify-correct loop for PDF-to-markdown extraction."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, NamedTuple

from pdf2md.providers.base import VerifyCorrection, VerifyResult, VLMProvider

logger = logging.getLogger(__name__)

_VERIFY_PROMPT = """\
You are verifying a PDF-to-markdown extraction. Compare the extracted \
markdown against the original page image.

Check for:
1. Missing text (paragraphs, sentences, words dropped)
2. Table structure errors (wrong columns, merged cells lost)
3. Math/equation errors (wrong symbols, broken LaTeX)
4. Reading order errors (columns mixed, captions misplaced)
5. Figure/caption association errors

Here is the extracted markdown:

---
{markdown}
---

Respond with ONLY a JSON object (no extra text):
{{"status": "pass" or "fail", "confidence": 0.0-1.0, "corrections": [...]}}

Each correction must include:
- before_context: ~30 chars from the markdown immediately before the bad text
- after_context: ~30 chars immediately after
- original: the exact text to fix (must appear verbatim in the markdown)
- replacement: the corrected text
- region: optional short label of where the fix applies

The before/after contexts make the location unambiguous. Do not paraphrase.
Copy the surrounding characters from the markdown above exactly, including \
whitespace and punctuation. If you cannot find the exact text in the \
markdown, omit that correction rather than guessing.

Each correction object looks like:
{{"region": "<short label>", "before_context": "<~30 chars before>", \
"after_context": "<~30 chars after>", "original": "<exact bad text>", \
"replacement": "<corrected text>"}}
"""


def _coerce_correction(raw: Any) -> VerifyCorrection | None:
    """Convert one correction dict (new or legacy shape) into a model.

    The new shape uses ``before_context`` / ``after_context`` / ``original`` /
    ``replacement``. The legacy shape used ``problem`` / ``fix``: those map to
    ``original`` / ``replacement`` with empty contexts (so the patch will only
    apply when ``original`` is unambiguous in the markdown).
    """
    if isinstance(raw, VerifyCorrection):
        return raw
    if not isinstance(raw, dict):
        return None

    original = raw.get("original")
    replacement = raw.get("replacement")
    if original is None and "problem" in raw:
        original = raw.get("problem")
    if replacement is None and "fix" in raw:
        replacement = raw.get("fix")

    if not original or replacement is None:
        return None

    try:
        return VerifyCorrection(
            region=str(raw.get("region", "") or ""),
            before_context=str(raw.get("before_context", "") or ""),
            after_context=str(raw.get("after_context", "") or ""),
            original=str(original),
            replacement=str(replacement),
        )
    except Exception:
        return None


def _coerce_corrections(raw_list: Any) -> list[VerifyCorrection]:
    if not isinstance(raw_list, list):
        return []
    out: list[VerifyCorrection] = []
    for item in raw_list:
        coerced = _coerce_correction(item)
        if coerced is not None:
            out.append(coerced)
    return out


def _build_verify_result(data: dict) -> VerifyResult:
    return VerifyResult(
        status=data.get("status", "pass"),
        confidence=float(data.get("confidence", 0.5)),
        corrections=_coerce_corrections(data.get("corrections", [])),
    )


def _parse_verify_response(response: str) -> VerifyResult:
    """Parse VLM response into a VerifyResult, handling non-JSON gracefully."""
    text = response.strip()

    # Try direct JSON parse
    try:
        data = json.loads(text)
        return _build_verify_result(data)
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Try to find JSON object in the response
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return _build_verify_result(data)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # Non-JSON response: default to pass with moderate confidence
    return VerifyResult(status="pass", confidence=0.5, corrections=[])


def verify_page(
    page_image: bytes,
    extracted_markdown: str,
    provider: VLMProvider,
) -> VerifyResult:
    """Verify extracted markdown against the original page image.

    Sends the page image and markdown to a VLM, asking it to compare them
    and report any discrepancies.

    Args:
        page_image: PNG bytes of the rendered page.
        extracted_markdown: The markdown text to verify.
        provider: VLM provider for the verification call.

    Returns:
        A VerifyResult with status, confidence, and any corrections.
    """
    prompt = _VERIFY_PROMPT.format(markdown=extracted_markdown)

    try:
        response = provider.complete_sync(prompt, image=page_image)
        return _parse_verify_response(response)
    except Exception as exc:
        logger.warning("Verification failed: %s", exc)
        return VerifyResult(
            status="error",
            confidence=0.0,
            corrections=[],
            explanation=f"Verification failed due to provider error: {exc}",
        )


class ApplyCorrectionsResult(NamedTuple):
    """Outcome of applying a batch of structured corrections."""

    applied: int
    skipped_no_match: int
    skipped_ambiguous: int

    def as_dict(self) -> dict[str, int]:
        return {
            "applied": self.applied,
            "skipped_no_match": self.skipped_no_match,
            "skipped_ambiguous": self.skipped_ambiguous,
        }


def _apply_corrections(
    markdown: str,
    corrections: list[VerifyCorrection] | list[dict],
) -> tuple[str, ApplyCorrectionsResult]:
    """Apply structured corrections to markdown.

    For each correction, search for ``before_context + original + after_context``
    in the markdown. If that combined needle occurs exactly once, replace the
    ``original`` portion with ``replacement`` (keeping the contexts intact).
    Skip with a warning otherwise.

    Returns:
        ``(corrected_markdown, ApplyCorrectionsResult)`` where the second item
        records counts of applied and skipped patches.
    """
    corrected = markdown
    applied = 0
    skipped_no_match = 0
    skipped_ambiguous = 0

    for raw in corrections:
        patch = _coerce_correction(raw)
        if patch is None:
            skipped_no_match += 1
            logger.warning(
                "verify: skipping malformed correction: %r", raw,
            )
            continue
        if not patch.original:
            skipped_no_match += 1
            continue

        needle = patch.before_context + patch.original + patch.after_context
        count = corrected.count(needle)
        if count == 0:
            skipped_no_match += 1
            logger.warning(
                "verify: correction not located (region=%r): %r -> %r",
                patch.region,
                patch.original,
                patch.replacement,
            )
            continue
        if count > 1:
            skipped_ambiguous += 1
            logger.warning(
                "verify: correction ambiguous, %d matches "
                "(region=%r): %r -> %r",
                count,
                patch.region,
                patch.original,
                patch.replacement,
            )
            continue

        # Unique location — splice in the replacement, keeping contexts.
        new_needle = (
            patch.before_context + patch.replacement + patch.after_context
        )
        corrected = corrected.replace(needle, new_needle, 1)
        applied += 1

    return corrected, ApplyCorrectionsResult(
        applied=applied,
        skipped_no_match=skipped_no_match,
        skipped_ambiguous=skipped_ambiguous,
    )


def run_verify_loop(
    page_image: bytes,
    extracted_markdown: str,
    provider: VLMProvider,
    max_rounds: int = 2,
    on_patch_summary: Callable[[ApplyCorrectionsResult], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> tuple[str, float]:
    """Run the agentic verify-correct loop.

    Verifies the markdown against the page image. If the verifier finds
    issues, applies corrections and re-verifies, up to ``max_rounds`` times.

    If the verifier returns ``status == "error"`` (a provider failure),
    the loop terminates immediately without applying corrections and
    returns the original markdown with confidence ``0.0``. The error
    explanation is forwarded through ``on_error`` so callers can surface
    the failure into ``Document.warnings`` instead of having every page
    silently degrade to the unverified text.

    Args:
        page_image: PNG bytes of the rendered page.
        extracted_markdown: Initial markdown to verify.
        provider: VLM provider for verification and correction calls.
        max_rounds: Maximum number of verify-correct iterations.
        on_patch_summary: Optional callback invoked once per round that
            attempted corrections, receiving the
            :class:`ApplyCorrectionsResult` for that round. Useful for
            surfacing skipped-correction counts into ``Document.warnings``
            without changing the return type.
        on_error: Optional callback invoked exactly once when the verifier
            terminates because the provider raised. Receives the explanation
            string from :class:`VerifyResult`.

    Returns:
        Tuple of ``(best_markdown, confidence)``. Patch outcomes are reported
        through ``on_patch_summary`` (and at WARNING log level) — the return
        type is unchanged for backwards compatibility.
    """
    current_markdown = extracted_markdown
    best_markdown = extracted_markdown
    best_confidence = 0.0

    for _round_num in range(max_rounds):
        result = verify_page(page_image, current_markdown, provider)

        # Provider error: do not apply corrections, terminate immediately
        if result.status == "error":
            if on_error is not None:
                try:
                    on_error(result.explanation or "verifier provider error")
                except Exception:
                    logger.exception("on_error callback failed")
            return extracted_markdown, 0.0

        # Track the best result
        if result.confidence > best_confidence:
            best_confidence = result.confidence
            best_markdown = current_markdown

        # If pass or no corrections, we are done
        if result.status == "pass" or not result.corrections:
            return current_markdown, result.confidence

        # Apply corrections and loop for re-verification
        current_markdown, summary = _apply_corrections(
            current_markdown, result.corrections,
        )
        if on_patch_summary is not None:
            try:
                on_patch_summary(summary)
            except Exception:
                logger.exception("on_patch_summary callback failed")

    # Loop exhausted. ``best_markdown`` was captured BEFORE the final
    # round's corrections, so returning it would discard them. Trust the
    # verifier's last-applied corrections — that's what the loop was for.
    if current_markdown != best_markdown:
        return current_markdown, best_confidence
    return best_markdown, best_confidence
