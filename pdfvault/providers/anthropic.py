"""Anthropic VLM provider using the Messages API."""
from __future__ import annotations
import base64
import os
import httpx

from pdfvault.cache import cached_call
from pdfvault.providers._ratelimit import RateLimiter, is_429_or_529


class AnthropicProvider:
    """Anthropic Claude provider via the Messages REST API."""

    _DEFAULT_MODEL = "claude-haiku-4-5-20251001"
    _BASE_URL = "https://api.anthropic.com/v1/messages"
    _API_VERSION = "2023-06-01"

    def __init__(self, model: str | None = None) -> None:
        self._model = model or self._DEFAULT_MODEL
        # Standard tier comfortably handles 2 RPS; 0.5s spacing leaves headroom
        # and 529 (overloaded) is treated like a transient rate-limit hit.
        self._limiter = RateLimiter(
            min_interval_s=0.5, max_retries=3, retry_on=is_429_or_529,
        )

    @property
    def name(self) -> str:
        return "anthropic"

    def _build_payload(self, prompt: str, image: bytes | None) -> dict:
        content: list[dict] = []
        if image is not None:
            from pdfvault.providers.base import detect_image_mime
            encoded = base64.b64encode(image).decode("utf-8")
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": detect_image_mime(image),
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
        def _call() -> str:
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

        return cached_call(
            lambda: self._limiter.call(_call),
            prompt=prompt, model=self._model, image=image, provider=self.name,
        )

    async def complete(self, prompt: str, image: bytes | None = None) -> str:
        return self.complete_sync(prompt, image)
