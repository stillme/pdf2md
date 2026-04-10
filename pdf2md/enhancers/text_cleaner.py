"""Text cleaner — removes figure axis labels, gene lists, and panel annotations that leaked into body text."""

from __future__ import annotations

import re

# Patterns for lines that look like figure elements (not body text)
# Gene names: short alphanumeric identifiers (CamelCase or all-alpha with numbers)
_GENE_NAME_RE = re.compile(r'^[A-Za-z][a-z]*\d*[a-z]?\d*$')
# Axis tick labels: just numbers, possibly with decimals
_AXIS_NUMBER_RE = re.compile(r'^[\d\.\-\+]+$')
# Single letter or short abbreviation (panel labels, axis labels)
_SHORT_LABEL_RE = re.compile(r'^[A-Za-z]\d?$')
# Panel label followed by text (e.g., "a bShared genes", "c Set size")
_PANEL_PREFIX_RE = re.compile(r'^[a-z]\s+[a-z]', re.IGNORECASE)
# Cluster/group labels like "C1", "C2", "C3", "J1", "J2"
_CLUSTER_LABEL_RE = re.compile(r'^[A-Z]\d{1,2}$')

# Words that indicate real sentences (articles, prepositions, conjunctions, verbs)
_SENTENCE_WORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'have', 'has', 'had',
    'in', 'on', 'at', 'to', 'for', 'with', 'from', 'by', 'of', 'and',
    'or', 'but', 'that', 'which', 'this', 'these', 'those', 'we', 'our',
    'their', 'its', 'can', 'will', 'may', 'should', 'would', 'could',
    'not', 'been', 'being', 'do', 'does', 'did', 'also', 'however',
    'therefore', 'although', 'because', 'since', 'while', 'during',
    'between', 'through', 'about', 'into', 'within', 'across', 'along',
    'after', 'before', 'each', 'every', 'both', 'all', 'some', 'any',
    'no', 'more', 'most', 'other', 'such', 'only', 'than', 'then',
    'here', 'there', 'where', 'when', 'how', 'what', 'who', 'whom',
    'show', 'shows', 'shown', 'indicate', 'indicates', 'suggest',
    'suggests', 'demonstrate', 'demonstrates', 'reveal', 'reveals',
    'found', 'observed', 'identified', 'performed', 'used', 'using',
}


def _is_figure_label_line(line: str) -> bool:
    """Determine if a single line looks like a figure element label.

    Returns True for lines that appear to be:
    - Gene names (short alphanumeric identifiers)
    - Axis tick labels (just numbers)
    - Single letters or short abbreviations
    - Cluster labels (C1, C2, J1, etc.)
    """
    stripped = line.strip()
    if not stripped:
        return False

    # Too long to be a figure label
    if len(stripped) > 20:
        return False

    # Pure axis numbers
    if _AXIS_NUMBER_RE.match(stripped):
        return True

    # Single letter or short label
    if _SHORT_LABEL_RE.match(stripped):
        return True

    # Cluster label
    if _CLUSTER_LABEL_RE.match(stripped):
        return True

    # Check if it's a few short tokens that look like gene names
    tokens = stripped.split()
    if len(tokens) <= 3:
        all_gene_like = all(
            _GENE_NAME_RE.match(t) or _AXIS_NUMBER_RE.match(t) or _CLUSTER_LABEL_RE.match(t)
            for t in tokens
        )
        if all_gene_like:
            return True

    return False


def _line_has_sentence_structure(line: str) -> bool:
    """Check if a line has words indicating real sentence/prose content.

    Also treats lines ending with a period that are 15+ chars as sentences,
    since figure labels never end with periods.
    """
    stripped = line.strip()

    # Lines ending with a period and longer than 15 chars are likely sentences
    if stripped.endswith('.') and len(stripped) >= 15:
        return True

    words = stripped.lower().split()
    for w in words:
        # Strip punctuation from word edges for matching
        clean = w.strip('.,;:!?()[]{}"\'-')
        if clean in _SENTENCE_WORDS:
            return True
    return False


def _has_strong_sentence_structure(line: str) -> bool:
    """Stricter check requiring 2+ sentence words or a period-terminated sentence.

    Single words like "a", "and", "of" appear in figure annotations (panel labels,
    chemical names like "Di- and tri-peptides"). This check avoids breaking
    annotation blocks on those lone occurrences.
    """
    stripped = line.strip()

    if stripped.endswith('.') and len(stripped) >= 15:
        return True

    words = stripped.lower().split()
    count = 0
    for w in words:
        clean = w.strip('.,;:!?()[]{}"\'-')
        if clean in _SENTENCE_WORDS:
            count += 1
            if count >= 2:
                return True
    return False


def _is_figure_leak_block(lines: list[str], start: int, min_block_size: int = 3) -> tuple[bool, int]:
    """Check if a consecutive block of lines starting at `start` is a figure-leak block.

    Two detection modes:
    - Classic: 3+ lines where >60% are short (<15 chars), no sentence structure.
    - Annotation: 5+ consecutive lines with no strong sentence structure (2+ sentence
      words). Catches longer figure annotations like metabolite lists, pathway labels.

    Returns (is_block, end_index) where end_index is the line after the block.
    """
    first_stripped = lines[start].strip()
    if not first_stripped:
        return False, start
    # Strong sentence check: lines with 2+ sentence words are real prose
    if _has_strong_sentence_structure(first_stripped):
        return False, start
    # Cap first-line length at 60 chars (covers metabolite names, pathway terms)
    if len(first_stripped) > 60:
        return False, start

    short_count = 0
    total = 0

    i = start
    while i < len(lines):
        stripped = lines[i].strip()
        # Empty lines break the block
        if not stripped:
            break
        # Lines with strong sentence structure (2+ sentence words) break the block
        if _has_strong_sentence_structure(stripped):
            break
        # Lines >60 chars that aren't gene-like labels break the block
        if len(stripped) > 60 and not _is_figure_label_line(stripped):
            break
        total += 1
        if len(stripped) < 15:
            short_count += 1
        i += 1

    block_end = i

    if total < min_block_size:
        return False, start

    short_ratio = short_count / total if total > 0 else 0

    # Classic mode: 3+ lines, mostly short labels
    if short_ratio > 0.6:
        return True, block_end

    # Annotation mode: 6+ consecutive non-sentence lines with at least one
    # short line are likely figure annotations (metabolite names, transporter
    # substrates, pathway terms). The short-line requirement excludes author
    # blocks which also lack sentence structure but have longer lines.
    if total >= 6 and short_count >= 1:
        return True, block_end

    return False, start


def clean_figure_text(text: str) -> str:
    """Remove figure axis labels, gene lists, and panel annotations that leaked into body text.

    Uses conservative heuristics:
    1. Detect blocks of 3+ consecutive short lines without sentence structure
    2. Remove individual lines that match strong figure-label patterns AND are under 20 chars

    Real content is preserved — only strips when high confidence of figure-leak.
    """
    lines = text.split('\n')
    result: list[str] = []
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        # Check if this starts a figure-leak block (3+ consecutive short lines)
        is_block, block_end = _is_figure_leak_block(lines, i)
        if is_block:
            # Skip the entire block
            i = block_end
            continue

        # For individual lines: only strip if it's clearly a figure label
        # AND is under 20 chars AND doesn't look like part of a sentence
        if (
            stripped
            and len(stripped) <= 20
            and _is_figure_label_line(stripped)
            and not _line_has_sentence_structure(stripped)
        ):
            # Check context: if previous or next line is a real sentence,
            # this isolated short line is likely a figure remnant
            prev_is_sentence = (
                i > 0 and len(lines[i-1].strip()) > 30
                and _line_has_sentence_structure(lines[i-1])
            )
            next_is_sentence = (
                i + 1 < len(lines) and len(lines[i+1].strip()) > 30
                and _line_has_sentence_structure(lines[i+1])
            )
            # Only strip isolated figure labels between real text
            if prev_is_sentence or next_is_sentence:
                i += 1
                continue

        result.append(lines[i])
        i += 1

    return '\n'.join(result)
