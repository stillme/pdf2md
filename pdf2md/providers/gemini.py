"""Gemini VLM provider using REST API."""
from __future__ import annotations
import base64
import os
import httpx

from pdf2md.cache import cached_call
from pdf2md.providers._ratelimit import RateLimiter, is_429


class GeminiProvider:
    """Google Gemini provider using the generativelanguage REST API."""

    # gemini-2.0-flash returns 404 from the v1beta endpoint as of Apr 2026.
    # gemini-2.5-flash is the current GA fast multimodal model.
    _DEFAULT_MODEL = "gemini-2.5-flash"
    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, model: str | None = None) -> None:
        self._model = model or self._DEFAULT_MODEL
        # Gemini free tier is 15 RPM → 4s spacing keeps us safely under quota.
        self._limiter = RateLimiter(
            min_interval_s=4.0, max_retries=3, retry_on=is_429,
        )

    @property
    def name(self) -> str:
        return "gemini"

    def _build_payload(self, prompt: str, image: bytes | None) -> dict:
        parts: list[dict] = []
        if image is not None:
            encoded = base64.b64encode(image).decode("utf-8")
            from pdf2md.providers.base import detect_image_mime
            parts.append({
                "inline_data": {
                    "mime_type": detect_image_mime(image),
                    "data": encoded,
                }
            })
        parts.append({"text": prompt})
        return {"contents": [{"parts": parts}]}

    def complete_sync(self, prompt: str, image: bytes | None = None) -> str:
        def _call() -> str:
            api_key = os.environ.get("GEMINI_API_KEY", "")
            url = f"{self._BASE_URL}/{self._model}:generateContent"
            payload = self._build_payload(prompt, image)
            response = httpx.post(
                url, json=payload, params={"key": api_key}, timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

        return cached_call(
            lambda: self._limiter.call(_call),
            prompt=prompt, model=self._model, image=image, provider=self.name,
        )

    async def complete(self, prompt: str, image: bytes | None = None) -> str:
        return self.complete_sync(prompt, image)
