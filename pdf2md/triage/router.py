"""Engine selection and tier routing."""

from __future__ import annotations
from pdf2md.config import Tier


def select_tier(analysis, requested: Tier) -> Tier:
    if requested != Tier.AUTO:
        return requested
    if analysis.is_scanned:
        return Tier.STANDARD
    if analysis.complexity_score >= 0.5:
        return Tier.DEEP
    if analysis.complexity_score >= 0.2:
        return Tier.STANDARD
    return Tier.FAST


def select_engine(
    tier: Tier,
    has_text_layer: bool = True,
    available_engines: list[str] | None = None,
    has_tables: bool = False,
    is_scanned: bool = False,
    vlm_available: bool = False,
) -> list[str]:
    if available_engines is None:
        available_engines = ["pypdfium2", "pdfplumber"]

    engines: list[str] = []

    if tier == Tier.FAST:
        if has_text_layer and "pypdfium2" in available_engines:
            engines.append("pypdfium2")
        elif "pdfplumber" in available_engines:
            engines.append("pdfplumber")
        if has_tables and "pdfplumber" in available_engines and "pdfplumber" not in engines:
            engines.append("pdfplumber")

    elif tier in (Tier.STANDARD, Tier.DEEP):
        if is_scanned and vlm_available:
            engines.append("vlm")
        if "marker" in available_engines:
            engines.append("marker")
        elif "docling" in available_engines:
            engines.append("docling")
        elif has_text_layer and "pypdfium2" in available_engines:
            engines.append("pypdfium2")
        if "pdfplumber" in available_engines and "pdfplumber" not in engines:
            engines.append("pdfplumber")

    if not engines and "pypdfium2" in available_engines:
        engines.append("pypdfium2")

    return engines
