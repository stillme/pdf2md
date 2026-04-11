"""Figure caption extraction and matching."""

from __future__ import annotations

import re

from pdf2md.document import Figure

_NEXT_PAGE_CAPTION_RE = re.compile(
    r"^\s*see\s+(?:the\s+)?next\s+page\s+for\s+caption\.?\s*$",
    re.IGNORECASE,
)


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
    """Match extracted captions to Figure objects by figure number and page order.

    Strategy:
    1. Parse caption figure numbers; separate main from Extended Data captions.
    2. Prefer real duplicate captions over "See next page for caption" placeholders.
    3. Sort uncaptioned figures by page order (preserving extraction order within page).
    4. Match main captions to the first figures by page order.
    5. Match Extended Data captions to remaining figures by page order.
    """
    if not captions or not figures:
        return figures

    for fig, cap in _caption_figure_pairs(figures, captions, only_uncaptioned=True):
        fig.caption = cap["caption"]

    return figures


def sync_caption_alt_text(markdown: str, figures: list[Figure], captions: list[dict]) -> str:
    """Update figure image alt text with matched figure caption labels."""
    for fig, cap in _caption_figure_pairs(figures, captions, only_uncaptioned=False):
        alt_text = _caption_alt_text(cap)
        markdown = re.sub(
            rf"!\[[^\]]*\]\({re.escape(fig.id)}\)",
            f"![{alt_text}]({fig.id})",
            markdown,
            count=1,
        )
    return markdown


def _caption_figure_pairs(
    figures: list[Figure],
    captions: list[dict],
    *,
    only_uncaptioned: bool,
) -> list[tuple[Figure, dict]]:
    main_caps = _prefer_real_captions(sorted(
        [c for c in captions if not c["is_extended"]],
        key=lambda c: c["fig_num"],
    ))
    ext_caps = _prefer_real_captions(sorted(
        [c for c in captions if c["is_extended"]],
        key=lambda c: c["fig_num"],
    ))

    candidate_figures = [f for f in figures if not f.caption] if only_uncaptioned else list(figures)
    ordered_figures = sorted(
        candidate_figures,
        key=lambda f: (f.page, figures.index(f)),
    )

    main_figures = ordered_figures[:len(main_caps)]
    ext_figures = ordered_figures[len(main_caps):]

    return [
        *zip(main_figures, main_caps, strict=False),
        *zip(ext_figures, ext_caps, strict=False),
    ]


def _prefer_real_captions(captions: list[dict]) -> list[dict]:
    """Keep one caption per figure number, replacing placeholders when possible."""
    best_by_num: dict[int, dict] = {}
    for cap in captions:
        fig_num = cap["fig_num"]
        current = best_by_num.get(fig_num)
        if current is None or (
            _NEXT_PAGE_CAPTION_RE.match(current["caption"] or "")
            and not _NEXT_PAGE_CAPTION_RE.match(cap["caption"] or "")
        ):
            best_by_num[fig_num] = cap
    return [best_by_num[fig_num] for fig_num in sorted(best_by_num)]


def _caption_alt_text(caption: dict) -> str:
    prefix = "Extended Data Fig." if caption["is_extended"] else "Fig."
    caption_text = re.sub(r"<[^>]+>", "", caption["caption"])
    caption_text = re.sub(r"\s+", " ", caption_text).strip().replace("]", ")")
    panel_start = re.search(r"\.\s+(?=[a-z](?:[,.\u2013-]|\s))", caption_text)
    if panel_start:
        caption_text = caption_text[:panel_start.start() + 1]
    return f"{prefix} {caption['fig_num']} | {caption_text}"
