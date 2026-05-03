"""Figure enhancer — uses VLM to describe figures and optionally extract images."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image

from pdfvault.config import FigureMode
from pdfvault.document import Figure
from pdfvault.providers.base import VLMProvider

MAX_VLM_IMAGE_PIXELS = 1500  # max dimension for VLM input


def _resize_for_vlm(image_bytes: bytes) -> bytes:
    """Resize an image to fit VLM input limits, return as JPEG bytes."""
    img = Image.open(BytesIO(image_bytes))
    # Resize if larger than MAX_VLM_IMAGE_PIXELS on longest side
    w, h = img.size
    if max(w, h) > MAX_VLM_IMAGE_PIXELS:
        ratio = MAX_VLM_IMAGE_PIXELS / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    # Convert to RGB (drop alpha) and compress as JPEG
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()

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

        # Resize for VLM input limits and get description (non-fatal on error)
        try:
            try:
                vlm_image = _resize_for_vlm(image_bytes)
            except Exception:
                vlm_image = image_bytes  # fallback to original if resize fails
            description = provider.complete_sync(_DESCRIBE_PROMPT, image=vlm_image)
        except Exception as e:
            print(f"  VLM figure description failed for {fig.id}: {e}")
            results.append(fig)
            continue

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
