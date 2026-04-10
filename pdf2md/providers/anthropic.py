"""Anthropic VLM provider using the Messages API."""
from __future__ import annotations
import base64
import os
import httpx


class AnthropicProvider:
    """Anthropic Claude provider via the Messages REST API."""

    _DEFAULT_MODEL = "claude-sonnet-4-5-20250514"
    _BASE_URL = "https://api.anthropic.com/v1/messages"
    _API_VERSION = "2023-06-01"

    def __init__(self, model: str | None = None) -> None:
        self._model = model or self._DEFAULT_MODEL

    @property
    def name(self) -> str:
        return "anthropic"

    def _build_payload(self, prompt: str, image: bytes | None) -> dict:
        content: list[dict] = []
        if image is not None:
            encoded = base64.b64encode(image).decode("utf-8")
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": encoded,
                },
            })
        content.append({"type": "text", "text": prompt})
        return {
            "model": self._model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": content}],
        }

    def complete_sync(self, prompt: str, image: bytes | None = None) -> str:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        payload = self._build_payload(prompt, image)
        response = httpx.post(
            self._BASE_URL,
            json=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": self._API_VERSION,
                "content-type": "application/json",
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"]

    async def complete(self, prompt: str, image: bytes | None = None) -> str:
        return self.complete_sync(prompt, image)
