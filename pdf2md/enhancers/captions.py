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

    Multi-line captions are captured in full: everything from "Fig. N |" until
    the next "Fig. N+1 |" or a section heading or a blank line followed by
    non-caption content.

    Returns list of dicts with keys: fig_num, caption, is_extended, full_match.
    """
    captions: list[dict] = []

    lines = markdown.split("\n")
    header_re = re.compile(
        r"((?:Extended Data\s+)?)"  # group 1: optional "Extended Data" prefix
        r"(?:Fig(?:ure)?\.?\s*)"    # "Fig." or "Figure"
        r"(\d+)"                     # group 2: figure number
        r"\s*[|.:]\s*"              # separator: |, ., or :
        r"(.+)",                     # group 3: rest of caption on this line
        re.IGNORECASE,
    )

    # Heading pattern to stop caption accumulation
    heading_re = re.compile(r'^#{1,4}\s+')

    i = 0
    while i < len(lines):
        m = header_re.match(lines[i].strip())
        if m:
            is_extended = "extended data" in m.group(1).lower()
            fig_num = int(m.group(2))
            caption_parts = [m.group(3).strip()]

            # Accumulate continuation lines until we hit:
            # - A blank line (unless followed by more caption text)
            # - Another figure header (next Fig. N)
            # - A section heading (## ...)
            # - End of text
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                # Stop at next figure caption header
                if header_re.match(next_line):
                    break
                # Stop at section headings
                if heading_re.match(next_line):
                    break
                # Stop at blank line
                if not next_line:
                    break
                caption_parts.append(next_line)
                j += 1

            caption_text = " ".join(caption_parts)

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
    """Match extracted captions to Figure objects by figure number and page ordering.

    Strategy:
    1. Parse caption figure numbers; separate main from Extended Data captions.
    2. Sort uncaptioned figures by page order (preserving extraction order within page).
    3. Group figures: the N largest (by image data size, as proxy for main figures)
       are treated as main figures; the rest are Extended Data or supplementary.
    4. Match main caption N to the Nth main figure by page order.
    5. Match Extended Data captions to remaining figures by page order.
    """
    if not captions or not figures:
        return figures

    # Separate captions into main and extended
    main_caps = sorted(
        [c for c in captions if not c["is_extended"]],
        key=lambda c: c["fig_num"],
    )
    ext_caps = sorted(
        [c for c in captions if c["is_extended"]],
        key=lambda c: c["fig_num"],
    )

    # Figures without captions, in page order (preserving extraction order)
    uncaptioned = [f for f in figures if not f.caption]

    if not uncaptioned:
        return figures

    n_main = len(main_caps)

    if n_main > 0 and len(uncaptioned) > n_main:
        # Sort uncaptioned by size (largest = main figures)
        # Use image_base64 length as a proxy for image size
        def _fig_size(f: Figure) -> int:
            if f.image_base64:
                return len(f.image_base64)
            return 0

        # Identify main figures as the N largest by image size
        sized = sorted(uncaptioned, key=_fig_size, reverse=True)
        main_figs = sized[:n_main]
        ext_figs = sized[n_main:]

        # Sort main figures back by page order for matching
        main_figs.sort(key=lambda f: (f.page, figures.index(f)))
        ext_figs.sort(key=lambda f: (f.page, figures.index(f)))

        # Match main captions to main figures by order
        for i, cap in enumerate(main_caps):
            if i < len(main_figs):
                main_figs[i].caption = cap["caption"]

        # Match extended captions to remaining figures by order
        for i, cap in enumerate(ext_caps):
            if i < len(ext_figs):
                ext_figs[i].caption = cap["caption"]
    else:
        # Simple case: match all captions sequentially
        sorted_caps = sorted(captions, key=lambda c: (c["is_extended"], c["fig_num"]))
        for i, cap in enumerate(sorted_caps):
            if i < len(uncaptioned):
                uncaptioned[i].caption = cap["caption"]

    return figures
