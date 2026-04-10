"""Figure enhancer — uses VLM to describe figures and optionally extract images."""

from __future__ import annotations

import base64
from pathlib import Path

from pdf2md.config import FigureMode
from pdf2md.document import Figure
from pdf2md.providers.base import VLMProvider

_DESCRIBE_PROMPT = """\
Describe this scientific figure in 2-3 sentences. Focus on:
- What type of visualization it is (bar chart, scatter plot, heatmap, microscopy, etc.)
- What data or results it shows
- Key patterns or findings visible

Be factual and concise. Do not speculate beyond what is visible."""


def enhance_figures(
    figures: list[Figure],
    *,
    mode: FigureMode,
    provider: VLMProvider | None,
    output_dir: str | None = None,
) -> list[Figure]:
    """Enhance figures based on the selected mode.

    Args:
        figures: List of Figure objects from assembly.
        mode: How to handle figures (SKIP, CAPTION, DESCRIBE, EXTRACT).
        provider: VLM provider for description generation.
        output_dir: Directory for saving extracted images (EXTRACT mode).

    Returns:
        Updated list of Figure objects.
    """
    if mode in (FigureMode.SKIP, FigureMode.CAPTION):
        # SKIP and CAPTION modes return figures unchanged
        return figures

    if mode in (FigureMode.DESCRIBE, FigureMode.EXTRACT):
        return _describe_figures(figures, provider=provider, output_dir=output_dir, extract=mode == FigureMode.EXTRACT)

    return figures


def _describe_figures(
    figures: list[Figure],
    *,
    provider: VLMProvider | None,
    output_dir: str | None = None,
    extract: bool = False,
) -> list[Figure]:
    """Send each figure's image to VLM for description."""
    results: list[Figure] = []

    for fig in figures:
        # Skip figures without image data
        if not fig.image_base64 or provider is None:
            results.append(fig)
            continue

        # Decode image for VLM
        image_bytes = base64.b64decode(fig.image_base64)

        # Get VLM description
        description = provider.complete_sync(_DESCRIBE_PROMPT, image=image_bytes)

        updates: dict = {"description": description}

        # In EXTRACT mode, also save image to disk
        if extract and output_dir is not None:
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            image_file = out_path / f"{fig.id}.png"
            image_file.write_bytes(image_bytes)
            updates["image_path"] = str(image_file)

        results.append(fig.model_copy(update=updates))

    return results
