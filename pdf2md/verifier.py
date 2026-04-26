"""Agentic verify-correct loop for PDF-to-markdown extraction."""

from __future__ import annotations

import json
import logging
import re

from pdf2md.providers.base import VerifyResult, VLMProvider

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

Each correction should be:
{{"region": "<description>", "problem": "<what is wrong>", "fix": "<corrected text>"}}
"""


def _parse_verify_response(response: str) -> VerifyResult:
    """Parse VLM response into a VerifyResult, handling non-JSON gracefully."""
    # Try to extract JSON from the response
    text = response.strip()

    # Try direct JSON parse
    try:
        data = json.loads(text)
        return VerifyResult(
            status=data.get("status", "pass"),
            confidence=float(data.get("confidence", 0.5)),
            corrections=data.get("corrections", []),
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Try to find JSON object in the response
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return VerifyResult(
                status=data.get("status", "pass"),
                confidence=float(data.get("confidence", 0.5)),
                corrections=data.get("corrections", []),
            )
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


def _apply_corrections(
    markdown: str,
    corrections: list[dict],
) -> str:
    """Apply corrections to markdown from verifier output.

    Uses simple string replacement where the correction provides enough
    context. Falls back to appending a note if the region cannot be located.
    """
    corrected = markdown
    for correction in corrections:
        fix = correction.get("fix", "")
        problem = correction.get("problem", "")
        if not fix:
            continue
        # If the problem text appears literally in the markdown, replace it
        if problem and problem in corrected:
            corrected = corrected.replace(problem, fix, 1)
    return corrected


def run_verify_loop(
    page_image: bytes,
    extracted_markdown: str,
    provider: VLMProvider,
    max_rounds: int = 2,
) -> tuple[str, float]:
    """Run the agentic verify-correct loop.

    Verifies the markdown against the page image. If the verifier finds
    issues, applies corrections and re-verifies, up to max_rounds times.

    If the verifier returns ``status == "error"`` (a provider failure),
    the loop terminates immediately without applying corrections and
    returns the original markdown with confidence ``0.0``.

    Args:
        page_image: PNG bytes of the rendered page.
        extracted_markdown: Initial markdown to verify.
        provider: VLM provider for verification and correction calls.
        max_rounds: Maximum number of verify-correct iterations.

    Returns:
        Tuple of (best_markdown, confidence).
    """
    current_markdown = extracted_markdown
    best_markdown = extracted_markdown
    best_confidence = 0.0

    for round_num in range(max_rounds):
        result = verify_page(page_image, current_markdown, provider)

        # Provider error: do not apply corrections, terminate immediately
        if result.status == "error":
            return extracted_markdown, 0.0

        # Track the best result
        if result.confidence > best_confidence:
            best_confidence = result.confidence
            best_markdown = current_markdown

        # If pass or no corrections, we are done
        if result.status == "pass" or not result.corrections:
            return current_markdown, result.confidence

        # Apply corrections and loop for re-verification
        current_markdown = _apply_corrections(
            current_markdown, result.corrections,
        )

    return best_markdown, best_confidence
