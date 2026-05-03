"""Build lightweight figure index sidecars from converted documents."""

from __future__ import annotations

import base64
import hashlib
import re

from pdfvault.document import Figure, FigureIndexEntry, FigureMention
from pdfvault.enhancers.captions import extract_panel_references

_FIGURE_MARKER_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<id>[^)]+)\)")
_CAPTION_LABEL_RE = re.compile(
    r"^(?P<extended>Extended Data\s+)?Fig\.\s+(?P<num>\d+)\s+\|\s*(?P<caption>.*)",
    re.IGNORECASE,
)
_PANEL_LABEL_RE = re.compile(r"(?:^|[.!?]\s+)(?P<panels>[a-z](?:[,\u2013-][a-z])*)\s*,")


def build_figure_index(
    markdown: str,
    figures: list[Figure],
) -> list[FigureIndexEntry]:
    """Create a compact, non-visual index for extracted figures.

    The index intentionally excludes inline image blobs. It is designed as a
    cheap artifact for downstream systems that need captions, labels, panel
    labels, and body mentions without pulling full document JSON.
    """
    if not figures:
        return []

    marker_meta = _extract_marker_metadata(markdown)
    mentions_by_key = _mentions_by_key(markdown)
    entries: list[FigureIndexEntry] = []

    for idx, fig in enumerate(figures, start=1):
        marker = marker_meta.get(fig.id, {})
        label_info = _label_info(marker.get("caption_line") or marker.get("alt") or "")
        figure_number = label_info.get("figure_number") or _id_number(fig.id)
        is_extended = bool(label_info.get("is_extended", False))
        label = label_info.get("label") or f"Figure {figure_number or idx}"
        caption = label_info.get("caption") or fig.caption
        panel_list = _merge_panels(
            _panels_from_caption(caption or ""),
            *[
                mention.panels
                for mention in mentions_by_key.get((figure_number, is_extended), [])
            ],
        )

        entries.append(FigureIndexEntry(
            figure_id=fig.id,
            label=label,
            figure_number=figure_number,
            is_extended=is_extended,
            page=fig.page,
            caption=caption,
            panels=panel_list,
            mentions=mentions_by_key.get((figure_number, is_extended), []),
            markdown_anchor=fig.id,
            markdown_line=marker.get("line"),
            image_hash=_image_hash(fig),
            image_path=fig.image_path,
            parse_confidence=_parse_confidence(fig, caption),
        ))

    return entries


def _extract_marker_metadata(markdown: str) -> dict[str, dict]:
    lines = markdown.splitlines()
    metadata: dict[str, dict] = {}
    for i, line in enumerate(lines):
        marker = _FIGURE_MARKER_RE.match(line.strip())
        if not marker:
            continue
        figure_id = marker.group("id")
        metadata[figure_id] = {
            "alt": marker.group("alt"),
            "line": i + 1,
            "caption_line": _next_caption_line(lines, i + 1),
        }
    return metadata


def _next_caption_line(lines: list[str], start: int) -> str | None:
    for line in lines[start:start + 3]:
        stripped = line.strip()
        if not stripped:
            continue
        return stripped if _CAPTION_LABEL_RE.match(stripped) else None
    return None


def _label_info(text: str) -> dict:
    match = _CAPTION_LABEL_RE.match(text.strip())
    if not match:
        return {}
    is_extended = bool(match.group("extended"))
    figure_number = int(match.group("num"))
    prefix = "Extended Data Fig." if is_extended else "Fig."
    return {
        "label": f"{prefix} {figure_number}",
        "figure_number": figure_number,
        "is_extended": is_extended,
        "caption": re.sub(r"\s+", " ", match.group("caption")).strip(),
    }


def _mentions_by_key(markdown: str) -> dict[tuple[int | None, bool], list[FigureMention]]:
    grouped: dict[tuple[int | None, bool], list[FigureMention]] = {}
    for ref in extract_panel_references(_body_markdown_for_mentions(markdown)):
        key = (ref.get("fig_num"), bool(ref.get("is_extended", False)))
        grouped.setdefault(key, []).append(FigureMention(
            panels=ref.get("panels", []),
            context=ref.get("context", ""),
        ))
    return grouped


def _body_markdown_for_mentions(markdown: str) -> str:
    return "\n".join(
        line
        for line in markdown.splitlines()
        if not _FIGURE_MARKER_RE.match(line.strip())
        and not _CAPTION_LABEL_RE.match(line.strip())
    )


def _panels_from_caption(caption: str) -> list[str]:
    panels: list[str] = []
    for match in _PANEL_LABEL_RE.finditer(caption):
        panels.extend(_expand_panel_string(match.group("panels")))
    return _dedupe(panels)


def _merge_panels(*panel_groups: list[str]) -> list[str]:
    panels: list[str] = []
    for group in panel_groups:
        panels.extend(group)
    return _dedupe(panels)


def _expand_panel_string(panel_str: str) -> list[str]:
    if "\u2013" in panel_str or "-" in panel_str:
        parts = re.split(r"[\u2013-]", panel_str.replace(",", "").replace(" ", ""))
        if len(parts) == 2 and len(parts[0]) == 1 and len(parts[1]) == 1:
            return [chr(c) for c in range(ord(parts[0]), ord(parts[1]) + 1)]
    return [p.strip() for p in re.split(r"[,\s]+", panel_str) if p.strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _id_number(figure_id: str) -> int | None:
    match = re.search(r"(\d+)$", figure_id)
    return int(match.group(1)) if match else None


def _image_hash(fig: Figure) -> str | None:
    if not fig.image_base64:
        return None
    try:
        image_bytes = base64.b64decode(fig.image_base64)
    except Exception:
        image_bytes = fig.image_base64.encode()
    return "sha256:" + hashlib.sha256(image_bytes).hexdigest()


def _parse_confidence(fig: Figure, caption: str | None) -> float:
    if fig.confidence:
        return fig.confidence
    return 0.9 if caption else 0.5
