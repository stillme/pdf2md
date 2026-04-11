"""Quality scorer for Nature gut adaptation paper (s41586-024-08216-z).

Measures the HARD problems: figure handling, text separation, structural quality.
Deterministic, pattern-based. No LLM calls.

Each dimension scores 0.0–1.0. Total is a weighted mean across all dimensions.
"""

from __future__ import annotations

import re


# ── Ground truth for the Nature paper ──────────────────────────────────

EXPECTED_TITLE = "Spatially restricted immune and microbiota-driven adaptation of the gut"
EXPECTED_DOI = "10.1038/s41586-024-08216-z"

EXPECTED_AUTHORS = [
    "Mayassi", "Li", "Segerstolpe", "Brown", "Weisberg",
    "Nakata", "Yano", "Herbst", "Artis", "Graham", "Xavier",
]

# The paper has 5 main figures + 10 Extended Data figures = 15 real figures.
EXPECTED_FIGURE_COUNT = 15
# Tolerance: figures within [10, 25] is OK; 58 is terrible.
FIGURE_COUNT_IDEAL_LOW = 10
FIGURE_COUNT_IDEAL_HIGH = 25

# Main figure captions that should be matched to figures
EXPECTED_MAIN_CAPTIONS = [
    "Fig. 1",   # Constructing the spatial transcriptome
    "Fig. 2",   # Spatial transcriptomics reveals microbiota-driven
    "Fig. 3",   # A model of spatiotemporal damage
    "Fig. 4",   # scRNA-seq coupled with spatial transcriptomics
    "Fig. 5",   # Immune-mediated control
]

EXPECTED_EXTENDED_CAPTIONS = [
    "Extended Data Fig. 1",
    "Extended Data Fig. 2",
    "Extended Data Fig. 3",
    "Extended Data Fig. 4",
    "Extended Data Fig. 5",
    "Extended Data Fig. 6",
    "Extended Data Fig. 7",
    "Extended Data Fig. 8",
    "Extended Data Fig. 9",
    "Extended Data Fig. 10",
]

# Section headings (from the paper's bold headings)
EXPECTED_HEADINGS = [
    "Constructing the spatial transcriptome",
    "The intestinal landscape is robust",
    "Spatially restricted adaptation",
    "cellular underpinnings",
    "Methods",
    "References",
]

# Compound words: good (should have hyphen) and bad (should not exist)
GOOD_COMPOUNDS = [
    "microbiota-driven", "region-enriched", "region-specific",
    "immune-mediated", "immune-driven", "single-cell", "co-housed",
]
BAD_JOINS = [
    "microbiotadriven", "regionenriched", "regionspecific",
    "immunemediated", "immunedriven", "singlecell",
]

# Figure annotation terms that should NOT appear in body text
FIGURE_LEAK_TERMS = [
    "Short chain fatty acids", "Adenosine triphosphate",
    "Adenosine diphosphate", "Beta-lactam antibiotics",
    "Gamma-aminobutyric acid", "Inorganic phosphate (monovalent)",
]

# Figure legend/statistical language that should NOT be in body text
# (it belongs in figure captions, not interleaved with prose)
LEGEND_LANGUAGE = [
    "scale bar,", "representative of n =", "biological replicate",
    "error bars represent", "processed using imagej",
    "see next page for caption",
]

# Key content phrases (text completeness)
KEY_PHRASES = [
    "spatial transcriptome", "murine intestine", "Visium",
    "circadian rhythm", "goblet cells", "enterocytes",
    "fibroblasts", "Crohn", "ulcerative colitis",
    "spatially restricted", "faecal microbiota transplant",
    "Patches and immune follicles",
]

# Superscript patterns that should be present
EXPECTED_SUPERSCRIPTS = [
    r"Mayassi<sup>\d", r"Li<sup>\d", r"Xavier<sup>\d",
    r"regions<sup>1",
]


# ── Scoring functions ──────────────────────────────────────────────────

def score_figure_count(md: str, figures: list | None = None) -> float:
    """Are we extracting the right NUMBER of figures?

    58 sub-panel images is terrible. 15 real figures is ideal.
    Score based on proximity to expected count.
    """
    # Count figure markers in markdown
    fig_count = len(re.findall(r'!\[', md))

    if FIGURE_COUNT_IDEAL_LOW <= fig_count <= FIGURE_COUNT_IDEAL_HIGH:
        return 1.0

    if fig_count < FIGURE_COUNT_IDEAL_LOW:
        # Too few — some figures missing
        return max(0.0, fig_count / FIGURE_COUNT_IDEAL_LOW)

    # Too many — over-extraction (sub-panels, icons, decorations)
    # Score degrades as count exceeds the ideal range
    overshoot = fig_count - FIGURE_COUNT_IDEAL_HIGH
    return max(0.0, 1.0 - overshoot * 0.03)  # -3% per extra figure


def score_figure_captions(md: str) -> float:
    """Are figure captions correctly matched?

    Checks that main "Fig. N" and "Extended Data Fig. N" captions appear
    as part of figure image alt text or immediately adjacent.
    "See next page for caption" as a caption is a FAILURE.
    """
    all_expected = EXPECTED_MAIN_CAPTIONS + EXPECTED_EXTENDED_CAPTIONS
    matched = 0
    for caption_prefix in all_expected:
        # Caption should appear in an image alt text: ![Fig. 1 | ...](figN)
        # OR immediately after a figure marker
        pattern = re.escape(caption_prefix)
        if re.search(rf'!\[{pattern}', md):
            matched += 1
        elif re.search(rf'{pattern}\s*\|', md):
            # Caption exists in text near a figure — partial credit
            matched += 0.5

    # Penalty for "See next page for caption" being used AS a caption
    bad_captions = len(re.findall(r'!\[See next page for caption', md))
    penalty = bad_captions * 0.05

    score = matched / len(all_expected) if all_expected else 0
    return max(0.0, min(1.0, score - penalty))


def score_figure_grouping(md: str) -> float:
    """Are sub-panel images grouped into composite figures?

    Consecutive figure markers with no body text between them indicate
    un-grouped sub-panels. A well-structured output has at most 1-2
    figures adjacent, with body text flowing between them.
    """
    lines = md.split("\n")
    consecutive_runs = []
    current_run = 0

    for line in lines:
        stripped = line.strip()
        if re.match(r'!\[', stripped):
            current_run += 1
        elif stripped:  # Non-empty, non-figure line
            if current_run > 0:
                consecutive_runs.append(current_run)
            current_run = 0
        # Empty lines don't break the run (figures separated by blank lines
        # are still a "dump")

    if current_run > 0:
        consecutive_runs.append(current_run)

    if not consecutive_runs:
        return 1.0

    # Score based on how many figures appear in "dumps" (runs > 2)
    total_figs = sum(consecutive_runs)
    dumped_figs = sum(r for r in consecutive_runs if r > 2)

    if total_figs == 0:
        return 1.0

    dump_ratio = dumped_figs / total_figs
    return max(0.0, 1.0 - dump_ratio)


def score_legend_separation(md: str) -> float:
    """Is figure legend/statistical text separated from body prose?

    Figure legends contain language like "Scale bar, 1000 um",
    "representative of n = 5 biological replicates", etc.
    These should be in figure captions, not in the body text flow.
    """
    lines = md.split("\n")
    body_lines = [l for l in lines if not re.match(r'\s*!\[', l)]
    body_text = "\n".join(body_lines).lower()

    leaks = sum(1 for phrase in LEGEND_LANGUAGE if phrase in body_text)
    # Also count annotation term leaks
    leaks += sum(1 for term in FIGURE_LEAK_TERMS if term in md)

    max_leaks = len(LEGEND_LANGUAGE) + len(FIGURE_LEAK_TERMS)
    return max(0.0, 1.0 - leaks / max_leaks)


def score_body_coherence(md: str) -> float:
    """Does the body text read as coherent prose?

    Checks for:
    - Mid-sentence figure interruptions (sentence broken by figure marker)
    - Orphaned sentence fragments after figure removals
    - Reading order disruptions
    """
    lines = md.split("\n")
    issues = 0
    total_checks = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or re.match(r'!\[', stripped) or stripped.startswith('#'):
            continue

        total_checks += 1

        # Lines that end mid-word or mid-sentence before a figure
        if i + 1 < len(lines):
            next_stripped = lines[i + 1].strip()
            if re.match(r'!\[', next_stripped):
                # Check if current line ends mid-sentence
                if stripped and not stripped[-1] in '.!?:;"\')':
                    issues += 1

        # Lines starting with lowercase after a figure (continuation fragment)
        if i > 0:
            prev_stripped = lines[i - 1].strip()
            if re.match(r'!\[', prev_stripped) or not prev_stripped:
                if stripped and stripped[0].islower() and len(stripped) > 5:
                    # Starts lowercase after figure — likely a broken continuation
                    issues += 0.5

    if total_checks == 0:
        return 1.0
    return max(0.0, 1.0 - issues / total_checks * 5)


def score_superscript_precision(md: str) -> float:
    """Are superscripts applied correctly WITHOUT false positives?

    Checks for:
    - Correct: Mayassi<sup>1,2,9</sup>, regions<sup>1-8</sup>
    - FALSE POSITIVE: fig<sup>1</sup>, tab<sup>1</sup>, Ang<sup>4</sup>
    """
    # Count correct superscripts
    correct = sum(1 for pat in EXPECTED_SUPERSCRIPTS if re.search(pat, md))
    correct_score = correct / len(EXPECTED_SUPERSCRIPTS) if EXPECTED_SUPERSCRIPTS else 0

    # Count false positives — superscripts in figure refs, gene names, etc.
    false_positives = 0
    false_positives += len(re.findall(r'fig<sup>', md, re.IGNORECASE))
    false_positives += len(re.findall(r'tab<sup>', md, re.IGNORECASE))
    false_positives += len(re.findall(r'eq<sup>', md, re.IGNORECASE))
    # Gene names getting superscripted (Ang<sup>4</sup>, Defa<sup>21</sup>).
    # Do not count expected short author names/affiliations, and require a
    # token boundary so valid acronyms like GCs<sup>32,33</sup> are not counted
    # by starting a match at the "Cs" substring.
    for match in re.finditer(r'\b([A-Z][a-z]{1,5})<sup>\d', md):
        if match.group(1) not in EXPECTED_AUTHORS:
            false_positives += 1

    precision_penalty = min(1.0, false_positives * 0.02)  # -2% per false positive
    return max(0.0, correct_score * 0.4 + (1.0 - precision_penalty) * 0.6)


def score_headings(md: str) -> float:
    """Score section heading detection."""
    md_lower = md.lower()
    found = sum(1 for h in EXPECTED_HEADINGS if h.lower() in md_lower)
    return found / len(EXPECTED_HEADINGS)


def score_hyphens(md: str) -> float:
    """Score compound word hyphen handling."""
    md_lower = md.lower()
    good_found = sum(1 for c in GOOD_COMPOUNDS if c in md_lower)
    good_score = good_found / len(GOOD_COMPOUNDS)
    bad_found = sum(1 for b in BAD_JOINS if b in md_lower)
    bad_penalty = bad_found / len(BAD_JOINS)
    return good_score * 0.6 + (1.0 - bad_penalty) * 0.4


def score_completeness(md: str) -> float:
    """Score presence of key scientific content."""
    md_lower = md.lower()
    found = sum(1 for p in KEY_PHRASES if p.lower() in md_lower)
    return found / len(KEY_PHRASES)


def score_metadata(md: str) -> float:
    """Score title, DOI, and basic author presence."""
    score = 0.0
    if EXPECTED_TITLE in md:
        score += 0.4
    if EXPECTED_DOI in md:
        score += 0.3
    header = md[:2000]
    authors_found = sum(1 for a in EXPECTED_AUTHORS if a in header)
    score += 0.3 * (authors_found / len(EXPECTED_AUTHORS))
    return min(1.0, score)


# ── Main scorer ────────────────────────────────────────────────────────

DIMENSIONS = {
    "figure_count": score_figure_count,
    "figure_captions": score_figure_captions,
    "figure_grouping": score_figure_grouping,
    "legend_separation": score_legend_separation,
    "body_coherence": score_body_coherence,
    "superscript_precision": score_superscript_precision,
    "headings": score_headings,
    "hyphens": score_hyphens,
    "completeness": score_completeness,
    "metadata": score_metadata,
}

# Weight dimensions by importance — figure quality is the hard problem
WEIGHTS = {
    "figure_count": 2.0,
    "figure_captions": 2.0,
    "figure_grouping": 2.0,
    "legend_separation": 1.5,
    "body_coherence": 1.5,
    "superscript_precision": 1.0,
    "headings": 1.0,
    "hyphens": 1.0,
    "completeness": 1.0,
    "metadata": 0.5,
}


def score_output(markdown: str) -> dict[str, float]:
    """Score markdown output across all quality dimensions.

    Returns dict of dimension_name -> score (0.0 to 1.0).
    Includes a "total" key with the weighted mean score.
    """
    scores = {}
    for name, fn in DIMENSIONS.items():
        scores[name] = round(fn(markdown), 3)

    # Weighted total
    weighted_sum = sum(scores[d] * WEIGHTS[d] for d in DIMENSIONS)
    total_weight = sum(WEIGHTS.values())
    scores["total"] = round(weighted_sum / total_weight, 3)
    return scores


def format_scores(scores: dict[str, float]) -> str:
    """Format scores as a readable table with weights."""
    lines = []
    for name in DIMENSIONS:
        value = scores.get(name, 0)
        weight = WEIGHTS.get(name, 1.0)
        bar = "#" * int(value * 20) + "." * (20 - int(value * 20))
        pct = f"{value * 100:5.1f}%"
        w = f"x{weight:.0f}" if weight != 1.0 else "  "
        lines.append(f"  {name:<24} [{bar}] {pct} {w}")

    total = scores.get("total", 0)
    lines.append(f"  {'TOTAL (weighted)':<24} {' ' * 22} {total * 100:5.1f}%")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
        md = data.get("markdown", "")
    else:
        md = sys.stdin.read()

    scores = score_output(md)
    print(format_scores(scores))
