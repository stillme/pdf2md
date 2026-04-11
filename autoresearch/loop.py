#!/usr/bin/env python3
"""Autoresearch loop — iteratively improves pdf2md quality.

Supports both Claude Code and Codex CLI as the coding agent.
Runs locally. No GPU, no VM needed.

Usage:
    cd /path/to/pdf2md
    uv run python autoresearch/loop.py [--iterations 10] [--dry-run]
    uv run python autoresearch/loop.py --agent codex --iterations 10
    uv run python autoresearch/loop.py --agent claude --iterations 10
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Force unbuffered output so we can tail the log
os.environ["PYTHONUNBUFFERED"] = "1"

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from autoresearch.scorer import score_output, format_scores, DIMENSIONS

# ── Config ─────────────────────────────────────────────────────────────

PDF_PATH = Path("~/Downloads/s41586-024-08216-z.pdf").expanduser()
LOG_DIR = PROJECT_ROOT / "autoresearch" / "runs"

# ── Agent configs ──────────────────────────────────────────────────────

AGENT_CONFIGS = {
    "claude": {
        "model_tiers": ["haiku", "sonnet", "opus"],
        "hard_minimum": 1,  # index into model_tiers for hard dimensions
    },
    "codex": {
        "model_tiers": ["gpt-5.4-mini", "gpt-5.4", "gpt-5.4"],
        "hard_minimum": 1,
    },
}

# Hard dimensions that need a stronger model from the start
HARD_DIMENSIONS = {
    "figure_count", "figure_captions", "figure_grouping",
    "legend_separation", "body_coherence",
}

# Max consecutive failures on one dimension before skipping to the next
MAX_FAILURES_PER_DIMENSION = 3

# Source files relevant to each quality dimension
DIMENSION_FILES = {
    "figure_count": ["pdf2md/extractors/pymupdf_ext.py", "pdf2md/core.py"],
    "figure_captions": ["pdf2md/enhancers/captions.py", "pdf2md/assembler.py"],
    "figure_grouping": ["pdf2md/extractors/pymupdf_ext.py", "pdf2md/assembler.py", "pdf2md/core.py"],
    "legend_separation": ["pdf2md/enhancers/text_cleaner.py", "pdf2md/assembler.py"],
    "body_coherence": ["pdf2md/assembler.py", "pdf2md/enhancers/text_cleaner.py"],
    "superscript_precision": ["pdf2md/enhancers/superscripts.py"],
    "headings": ["pdf2md/assembler.py", "pdf2md/extractors/pymupdf_ext.py"],
    "hyphens": ["pdf2md/assembler.py"],
    "completeness": ["pdf2md/assembler.py", "pdf2md/enhancers/text_cleaner.py"],
    "metadata": ["pdf2md/enhancers/metadata.py"],
}

# How many consecutive failures before escalating model tier
ESCALATION_THRESHOLD = 2


# ── Pipeline runner ────────────────────────────────────────────────────

def run_pipeline() -> tuple[str, float]:
    """Run pdf2md on the Nature paper and return (markdown, elapsed_seconds)."""
    t0 = time.monotonic()
    result = subprocess.run(
        ["uv", "run", "python", "-c", f"""
import json
from pdf2md.core import convert
doc = convert("{PDF_PATH}", tier="fast")
print(json.dumps({{"markdown": doc.markdown}}))
"""],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=300,
    )
    elapsed = time.monotonic() - t0

    if result.returncode != 0:
        print(f"  Pipeline FAILED: {result.stderr[:500]}")
        return "", elapsed

    try:
        data = json.loads(result.stdout)
        return data["markdown"], elapsed
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  Pipeline output parse error: {e}")
        return "", elapsed


def run_tests() -> bool:
    """Run the test suite. Returns True if all pass."""
    result = subprocess.run(
        ["uv", "run", "pytest", "-x", "-q", "--tb=short"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=120,
    )
    passed = result.returncode == 0
    if not passed:
        # Show last 10 lines of test output
        lines = result.stdout.strip().split("\n")
        print("  Test failures:")
        for line in lines[-10:]:
            print(f"    {line}")
    return passed


# ── Git helpers ────────────────────────────────────────────────────────

def git_has_changes() -> bool:
    result = subprocess.run(
        ["git", "diff", "--quiet"], cwd=str(PROJECT_ROOT),
    )
    return result.returncode != 0


def git_revert():
    """Revert all uncommitted changes."""
    subprocess.run(
        ["git", "checkout", "--", "."], cwd=str(PROJECT_ROOT),
        capture_output=True,
    )
    # Also remove any new untracked files in pdf2md/ and tests/
    subprocess.run(
        ["git", "clean", "-fd", "pdf2md/", "tests/"],
        cwd=str(PROJECT_ROOT), capture_output=True,
    )


def git_commit(message: str):
    subprocess.run(
        ["git", "add", "-A", "pdf2md/", "tests/"],
        cwd=str(PROJECT_ROOT), capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(PROJECT_ROOT), capture_output=True,
    )


# ── Prompt construction ────────────────────────────────────────────────

def build_prompt(
    dimension: str,
    score: float,
    scores: dict[str, float],
    markdown_excerpt: str,
    attempt: int,
) -> str:
    """Build the prompt for Claude Code to improve a quality dimension."""

    files = DIMENSION_FILES.get(dimension, [])
    files_str = ", ".join(files) if files else "the relevant enhancer/assembler modules"

    return f"""You are improving the pdf2md library's markdown output quality.

## Context
pdf2md converts scientific PDFs to structured markdown. We're optimizing quality
on a Nature paper (s41586-024-08216-z) using automated scoring.

## Current quality scores (0-100%)
{format_scores(scores)}

## Your task
Improve the **{dimension}** dimension (currently {score*100:.1f}%).

## Relevant source files
{files_str}

Read those files, understand the current logic, and make ONE focused change to
improve the {dimension} score. The change should be:
- Targeted — only modify what's needed for {dimension}
- Safe — must not regress other dimensions
- Tested — add or update tests for the change

## Scoring details for "{dimension}"
This dimension measures: {_dimension_description(dimension)}

## Current output excerpt (first 3000 chars)
```
{markdown_excerpt[:3000]}
```

## Rules
1. Read the relevant source files first
2. Make ONE focused change (not multiple unrelated changes)
3. Run `uv run pytest -x -q` to verify tests pass
4. Do NOT modify autoresearch/ files
5. Do NOT modify benchmark-outputs/ files
6. This is attempt #{attempt} for this dimension — if previous attempts failed,
   try a DIFFERENT approach

## What to output
After making your change and verifying tests pass, output a single line summary
of what you changed and why.
"""


def _dimension_description(dim: str) -> str:
    descriptions = {
        "figure_count": (
            "The paper has 5 main figures + 10 Extended Data figures = 15 real figures. "
            "If too many figures are found, sub-panel images may be treated as separate figures. "
            "Improve by increasing min_width/min_height thresholds in extract_figures(), merging "
            "sub-panel images by page proximity, or filtering out tiny decorative images. "
            "Target: 10-25 figure markers in the output. Score degrades 3% per extra figure beyond 25."
        ),
        "figure_captions": (
            "Main figure captions (Fig. 1 through Fig. 5) and Extended Data captions (Extended Data Fig. 1-10) "
            "should appear as the alt text in figure image markers: ![Fig. 1 | caption...](figN). "
            "Figures should not keep 'See next page for caption' placeholders as captions. "
            "The caption matching in enhancers/captions.py should use spatial proximity or page order "
            "to associate captions with the correct images."
        ),
        "figure_grouping": (
            "Multiple consecutive figure markers with no body text between them indicates un-grouped "
            "sub-panel images dumped in a row. Currently there are runs of 20+ figures in sequence. "
            "Fix by: grouping images from the same page into a single composite figure, filtering "
            "sub-panels, or using spatial analysis to determine which images belong together."
        ),
        "legend_separation": (
            "Figure legend/statistical text like 'Scale bar, 1000 um', 'representative of n = 5 "
            "biological replicates', 'See next page for caption' is appearing in the body text. "
            "This text should be in figure captions or stripped. The text_cleaner.py or assembler.py "
            "needs to detect and separate figure legend text from body prose."
        ),
        "body_coherence": (
            "Body text should flow as coherent prose without figure-related interruptions. "
            "Checks for: sentences broken mid-word before figure markers, orphaned fragments "
            "after figures (lines starting lowercase), and reading order disruptions."
        ),
        "superscript_precision": (
            "Superscripts should wrap citation refs (regions<sup>1-8</sup>) and author affiliations "
            "(Mayassi<sup>1,2,9</sup>) but NOT figure IDs (fig1 becoming fig<sup>1</sup>), gene names "
            "(Ang4 becoming Ang<sup>4</sup>), or other false positives. Fix the regex in "
            "enhancers/superscripts.py to exclude markdown image refs and known identifier patterns."
        ),
        "headings": "Whether section headings are correctly detected. Checks for known headings from the paper.",
        "hyphens": "Whether compound words keep hyphens and combining forms are joined. Penalizes bad joins.",
        "completeness": "Whether key scientific content phrases are present in the output.",
        "metadata": "Title, DOI, and author name presence in the header.",
    }
    return descriptions.get(dim, "General quality metric.")


# ── Agent invocation ───────────────────────────────────────────────────

def invoke_agent(prompt: str, model: str, agent: str = "claude") -> tuple[bool, str]:
    """Invoke a coding agent CLI to make a change. Returns (success, output)."""
    print(f"  Invoking {agent} ({model})...")

    if agent == "claude":
        cmd = [
            "claude", "-p", prompt,
            "--model", model,
            "--max-turns", "25",
            "--allowedTools", "Edit,Write,Read,Bash,Glob,Grep",
        ]
    elif agent == "codex":
        cmd = [
            "codex", "exec",
            "-m", model,
            "--full-auto",
            prompt,
        ]
    else:
        print(f"  Unknown agent: {agent}")
        return False, ""

    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=600,
    )

    output = result.stdout[-2000:] if result.stdout else ""
    success = result.returncode == 0
    return success, output


# ── Main loop ──────────────────────────────────────────────────────────

def run_loop(max_iterations: int = 10, dry_run: bool = False, agent: str = "claude"):
    """Main autoresearch loop."""

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"run_{run_id}.jsonl"

    agent_config = AGENT_CONFIGS[agent]
    model_tiers = agent_config["model_tiers"]
    hard_minimum = agent_config["hard_minimum"]

    print(f"=== Autoresearch Loop ===")
    print(f"Agent: {agent} (models: {' -> '.join(model_tiers)})")
    print(f"PDF: {PDF_PATH}")
    print(f"Max iterations: {max_iterations}")
    print(f"Log: {log_path}")
    print()

    # Track consecutive failures per dimension for model escalation
    failure_counts: dict[str, int] = {d: 0 for d in DIMENSIONS}
    # Track which dimensions have been maxed out (score = 1.0)
    maxed_dims: set[str] = set()
    # Track dimensions skipped after too many failures
    skipped_dims: set[str] = set()

    # Initial run
    print("[0] Running initial pipeline...")
    markdown, elapsed = run_pipeline()
    if not markdown:
        print("FATAL: Initial pipeline run failed. Exiting.")
        return

    scores = score_output(markdown)
    print(f"[0] Initial scores (pipeline: {elapsed:.1f}s):")
    print(format_scores(scores))
    print()

    _log(log_path, {"iteration": 0, "scores": scores, "action": "initial"})

    for i in range(1, max_iterations + 1):
        # Find weakest non-maxed, non-skipped dimension
        candidates = {
            d: s for d, s in scores.items()
            if d != "total" and d not in maxed_dims and d not in skipped_dims
        }
        if not candidates:
            print(f"[{i}] All dimensions maxed out. Done!")
            break

        dimension = min(candidates, key=candidates.get)
        score = candidates[dimension]

        if score >= 1.0:
            maxed_dims.add(dimension)
            continue

        # Skip dimensions that have failed too many times — move on, come back later
        fails = failure_counts[dimension]
        if fails >= MAX_FAILURES_PER_DIMENSION:
            skipped_dims.add(dimension)
            continue

        # Model routing: hard dimensions start at stronger model
        if dimension in HARD_DIMENSIONS:
            tier_idx = min(hard_minimum + fails // ESCALATION_THRESHOLD, len(model_tiers) - 1)
        else:
            tier_idx = min(fails // ESCALATION_THRESHOLD, len(model_tiers) - 1)
        model = model_tiers[tier_idx]

        print(f"[{i}] Target: {dimension} ({score*100:.1f}%) | agent: {agent} | model: {model}")

        if dry_run:
            print(f"  [dry-run] Would invoke {agent}. Skipping.")
            continue

        # Build prompt
        prompt = build_prompt(
            dimension=dimension,
            score=score,
            scores=scores,
            markdown_excerpt=markdown,
            attempt=fails + 1,
        )

        # Invoke agent
        agent_ok, agent_output = invoke_agent(prompt, model, agent=agent)

        if not agent_ok:
            print(f"  Agent failed (exit code). Reverting.")
            git_revert()
            failure_counts[dimension] += 1
            _log(log_path, {
                "iteration": i, "dimension": dimension, "model": model,
                "result": "agent_failed", "scores": scores,
            })
            continue

        if not git_has_changes():
            print(f"  Agent made no changes. Skipping.")
            failure_counts[dimension] += 1
            _log(log_path, {
                "iteration": i, "dimension": dimension, "model": model,
                "result": "no_changes", "scores": scores,
            })
            continue

        # Run tests
        print(f"  Running tests...")
        tests_ok = run_tests()
        if not tests_ok:
            print(f"  Tests failed. Reverting.")
            git_revert()
            failure_counts[dimension] += 1
            _log(log_path, {
                "iteration": i, "dimension": dimension, "model": model,
                "result": "tests_failed", "scores": scores,
            })
            continue

        # Re-run pipeline and score
        print(f"  Re-running pipeline...")
        new_markdown, new_elapsed = run_pipeline()
        if not new_markdown:
            print(f"  Pipeline failed after changes. Reverting.")
            git_revert()
            failure_counts[dimension] += 1
            continue

        new_scores = score_output(new_markdown)

        # Accept if target dimension improved AND no other dimension regressed
        target_improved = new_scores[dimension] > scores[dimension]
        any_regressed = any(
            new_scores[d] < scores[d] - 0.05  # 5% tolerance
            for d in DIMENSIONS if d != "total"
        )

        if target_improved and not any_regressed:
            delta = new_scores[dimension] - scores[dimension]
            total_delta = new_scores["total"] - scores["total"]
            print(f"  ACCEPTED: {dimension} +{delta*100:.1f}% | total +{total_delta*100:.1f}%")
            print(format_scores(new_scores))

            # Commit the improvement
            summary = agent_output.strip().split("\n")[-1][:100]
            git_commit(
                f"autoresearch: improve {dimension} "
                f"({scores[dimension]*100:.0f}% -> {new_scores[dimension]*100:.0f}%)\n\n"
                f"{summary}\n\n"
                f"Co-Authored-By: Claude Code <noreply@anthropic.com>"
            )

            scores = new_scores
            markdown = new_markdown
            failure_counts[dimension] = 0  # Reset on success

            _log(log_path, {
                "iteration": i, "dimension": dimension, "model": model,
                "result": "accepted", "delta": delta,
                "scores": new_scores,
            })
        else:
            reasons = []
            if not target_improved:
                reasons.append(f"{dimension} did not improve")
            if any_regressed:
                regressed = [
                    d for d in DIMENSIONS
                    if d != "total" and new_scores[d] < scores[d] - 0.05
                ]
                reasons.append(f"regressed: {', '.join(regressed)}")
            print(f"  REJECTED: {'; '.join(reasons)}. Reverting.")
            git_revert()
            failure_counts[dimension] += 1

            _log(log_path, {
                "iteration": i, "dimension": dimension, "model": model,
                "result": "rejected", "reason": "; ".join(reasons),
                "old_scores": scores, "new_scores": new_scores,
            })

        print()

    # Final summary
    print("=== Final Scores ===")
    print(format_scores(scores))
    print(f"\nLog: {log_path}")


def _log(path: Path, entry: dict):
    """Append a JSON line to the run log."""
    entry["timestamp"] = datetime.now().isoformat()
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Autoresearch loop for pdf2md quality")
    parser.add_argument("--iterations", type=int, default=10, help="Max iterations (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Score only, don't invoke agent")
    parser.add_argument("--agent", choices=["claude", "codex"], default="claude",
                        help="Coding agent CLI to use (default: claude)")
    args = parser.parse_args()

    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found at {PDF_PATH}")
        print("Download the Nature paper or update PDF_PATH in loop.py")
        sys.exit(1)

    if args.agent not in AGENT_CONFIGS:
        print(f"ERROR: Unknown agent '{args.agent}'. Available: {', '.join(AGENT_CONFIGS)}")
        sys.exit(1)

    run_loop(max_iterations=args.iterations, dry_run=args.dry_run, agent=args.agent)


if __name__ == "__main__":
    main()
