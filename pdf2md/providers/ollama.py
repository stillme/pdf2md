"""Ollama VLM provider for local inference."""
from __future__ import annotations
import base64
import httpx


class OllamaProvider:
    """Ollama provider for locally-hosted models via the generate API."""

    _DEFAULT_MODEL = "gemma3:12b"
    _BASE_URL = "http://localhost:11434/api/generate"

    def __init__(self, model: str | None = None) -> None:
        self._model = model or self._DEFAULT_MODEL

    @property
    def name(self) -> str:
        return "ollama"

    def _build_payload(self, prompt: str, image: bytes | None) -> dict:
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        if image is not None:
            encoded = base64.b64encode(image).decode("utf-8")
            payload["images"] = [encoded]
        return payload

    def complete_sync(self, prompt: str, image: bytes | None = None) -> str:
        payload = self._build_payload(prompt, image)
        response = httpx.post(
            self._BASE_URL,
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data["response"]

    async def complete(self, prompt: str, image: bytes | None = None) -> str:
        return self.complete_sync(prompt, image)
