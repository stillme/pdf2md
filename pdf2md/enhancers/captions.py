"""Figure caption extraction and matching."""

from __future__ import annotations

import re

from pdf2md.document import Figure


def extract_figure_captions(markdown: str) -> list[dict]:
    """Extract figure captions/legends from markdown text.

    Matches patterns like:
    - "Fig. 1 | Caption text here."
    - "Figure 2. Caption text."
    - "Fig. 3: Caption text."
    - "Extended Data Fig. 1 | Caption text."

    Returns list of dicts with keys: fig_num, caption, is_extended, full_match.
    """
    captions: list[dict] = []

    # Split on lines to avoid greedy matching across figure captions.
    # Process each line individually, then handle multi-line captions
    # by accumulating continuation lines.
    lines = markdown.split("\n")
    header_re = re.compile(
        r"((?:Extended Data\s+)?)"  # group 1: optional "Extended Data" prefix
        r"(?:Fig(?:ure)?\.?\s*)"    # "Fig." or "Figure"
        r"(\d+)"                     # group 2: figure number
        r"\s*[|.:]\s*"              # separator: |, ., or :
        r"(.+)",                     # group 3: rest of caption on this line
        re.IGNORECASE,
    )

    i = 0
    while i < len(lines):
        m = header_re.match(lines[i].strip())
        if m:
            is_extended = "extended data" in m.group(1).lower()
            fig_num = int(m.group(2))
            caption_parts = [m.group(3).strip()]

            # Accumulate continuation lines until we hit a blank line,
            # another figure header, or end of text
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line or header_re.match(next_line):
                    break
                caption_parts.append(next_line)
                j += 1

            caption_text = " ".join(caption_parts)
            # Trim to first sentence if very long (keep up to first period after 20+ chars)
            if len(caption_text) > 200:
                period_pos = caption_text.find(".", 20)
                if period_pos > 0:
                    caption_text = caption_text[: period_pos + 1]

            full_match = lines[i].strip()

            captions.append({
                "fig_num": fig_num,
                "caption": caption_text,
                "is_extended": is_extended,
                "full_match": full_match,
            })
            i = j
        else:
            i += 1

    return captions


def extract_panel_references(markdown: str) -> list[dict]:
    """Extract in-text figure panel references like 'Fig. 3a', 'Fig. 4c,d'.

    Returns list of dicts with keys: fig_num, panels, context.
    """
    refs: list[dict] = []

    # Match "Fig. 3a" or "Fig. 3a,b" or "Fig. 3a-c" or "Fig. 3a,b,c"
    # The panel part: a single letter optionally followed by comma/dash/en-dash + letter
    pattern = re.compile(
        r"Fig\.?\s*(\d+)([a-z](?:[,\u2013-][a-z])*)",
        re.IGNORECASE,
    )

    for match in pattern.finditer(markdown):
        fig_num = int(match.group(1))
        panel_str = match.group(2)

        # Parse panels: "a,b" -> ["a", "b"], "a-c" -> ["a", "b", "c"]
        panels = _parse_panels(panel_str)

        # Get surrounding context (40 chars before and after)
        start = max(0, match.start() - 40)
        end = min(len(markdown), match.end() + 40)
        context = markdown[start:end].replace("\n", " ").strip()

        refs.append({
            "fig_num": fig_num,
            "panels": panels,
            "context": context,
        })

    return refs


def _parse_panels(panel_str: str) -> list[str]:
    """Parse a panel string like 'a,b', 'a-c', or 'a' into a list of panel letters."""
    # Check for range: a-c or a\u2013c (en-dash)
    if "\u2013" in panel_str or "-" in panel_str:
        parts = re.split(r"[\u2013-]", panel_str.replace(",", "").replace(" ", ""))
        if len(parts) == 2 and len(parts[0]) == 1 and len(parts[1]) == 1:
            return [chr(c) for c in range(ord(parts[0]), ord(parts[1]) + 1)]
    # Comma-separated or individual
    panels = [p.strip() for p in re.split(r"[,\s]+", panel_str) if p.strip()]
    return panels


def match_captions_to_figures(
    figures: list[Figure],
    captions: list[dict],
) -> list[Figure]:
    """Match extracted captions to Figure objects by figure number ordering.

    Assigns captions to figures sequentially: caption for Fig. 1 goes to the
    first figure without a caption, Fig. 2 to the second, etc. When multiple
    figures share a page, they are matched in order.
    """
    if not captions or not figures:
        return figures

    # Sort captions by figure number, extended data figures last
    sorted_caps = sorted(captions, key=lambda c: (c["is_extended"], c["fig_num"]))

    # Figures without captions, in page order (preserving extraction order)
    uncaptioned = [f for f in figures if not f.caption]

    # Match by index: caption 0 -> uncaptioned figure 0, etc.
    for i, cap in enumerate(sorted_caps):
        if i < len(uncaptioned):
            uncaptioned[i].caption = cap["caption"]

    return figures
