"""Configuration for pdfvault."""

from __future__ import annotations

import os
from enum import Enum

from pydantic import BaseModel, model_validator


class Tier(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"
    AUTO = "auto"


class FigureMode(str, Enum):
    SKIP = "skip"
    CAPTION = "caption"
    DESCRIBE = "describe"
    EXTRACT = "extract"


class Config(BaseModel):
    tier: Tier = Tier.AUTO
    figures: FigureMode = FigureMode.CAPTION
    # Equation extraction calls a VLM once per math-heavy page. Disable
    # for batch jobs on text-heavy corpora (biomedical, social sciences)
    # — those papers rarely have meaningful math but the heuristic still
    # fires on isolated Greek letters or ``=`` characters and burns
    # subscription quota / API spend.
    equations: bool = True
    verify: bool = True
    provider: str | None = None
    output_dir: str | None = None
    max_concurrent_pages: int = 4
    max_verify_rounds: int = 2
    timeout_per_page: int = 60

    @model_validator(mode="before")
    @classmethod
    def load_env_defaults(cls, data: dict) -> dict:
        if isinstance(data, dict):
            env_map = {
                "tier": "PDFVAULT_TIER",
                "figures": "PDFVAULT_FIGURES",
                "provider": "PDFVAULT_PROVIDER",
                "equations": "PDFVAULT_EQUATIONS",
            }
            for field, env_var in env_map.items():
                if field not in data or data[field] is None:
                    val = os.environ.get(env_var)
                    if val is not None:
                        data[field] = val
            # Coerce env-string equations to bool.
            eq = data.get("equations")
            if isinstance(eq, str):
                data["equations"] = eq.lower() in ("1", "true", "yes", "on")
        return data
