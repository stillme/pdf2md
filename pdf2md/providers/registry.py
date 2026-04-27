"""VLM provider auto-detection and instantiation.

Default model selection is biased for cost — the headline use case is
batch-processing thousands of papers, so per-paper $/page matters more
than peak per-call quality. Indicative pricing as of Apr 2026:

    gemini-2.5-flash       $0.30 in / $2.50 out per 1M tok    (default)
    gemini-2.5-flash-lite  $0.10 in / $0.40 out per 1M tok
    gemini-2.5-pro         $1.25 in / $10.0 out per 1M tok
    gpt-4o-mini            $0.15 in / $0.60 out per 1M tok    (OpenAI default)
    gpt-4o                 $2.50 in / $10.0 out per 1M tok
    claude-haiku-4-5       $1.00 in / $5.00 out per 1M tok    (Anthropic default)

Override per-call with ``provider="<name>/<model_id>"`` —
e.g. ``provider="gemini/gemini-2.5-pro"`` for the strongest verifier.

Per-task model routing (cheap model for figure descriptions, capable
model for verification) is a planned follow-up — currently every VLM
call shares one provider.
"""
from __future__ import annotations
import os
from pdf2md.providers.base import VLMProvider


def detect_providers() -> list[dict]:
    providers = []
    providers.append({
        "name": "gemini",
        "available": bool(os.environ.get("GEMINI_API_KEY")),
        "env_var": "GEMINI_API_KEY",
        "default_model": "gemini-2.5-flash",
    })
    providers.append({
        "name": "anthropic",
        "available": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "env_var": "ANTHROPIC_API_KEY",
        "default_model": "claude-haiku-4-5-20251001",
    })
    providers.append({
        "name": "openai",
        "available": bool(os.environ.get("OPENAI_API_KEY")),
        "env_var": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
    })
    ollama_available = False
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=2)
        ollama_available = r.status_code == 200
    except Exception:
        pass
    providers.append({
        "name": "ollama",
        "available": ollama_available,
        "default_model": "gemma3:12b",
    })
    return providers


def get_provider(provider_string: str | None = None) -> VLMProvider | None:
    if provider_string:
        parts = provider_string.split("/", 1)
        provider_name = parts[0]
        model = parts[1] if len(parts) > 1 else None
    else:
        available = detect_providers()
        found = next((p for p in available if p["available"]), None)
        if not found:
            return None
        provider_name = found["name"]
        model = found["default_model"]

    if provider_name in ("gemini", "google"):
        from pdf2md.providers.gemini import GeminiProvider
        return GeminiProvider(model=model)
    elif provider_name == "anthropic":
        from pdf2md.providers.anthropic import AnthropicProvider
        return AnthropicProvider(model=model)
    elif provider_name == "openai":
        from pdf2md.providers.openai import OpenAIProvider
        return OpenAIProvider(model=model)
    elif provider_name == "ollama":
        from pdf2md.providers.ollama import OllamaProvider
        return OllamaProvider(model=model)
    return None
