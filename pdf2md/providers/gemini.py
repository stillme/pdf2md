"""Gemini VLM provider using REST API."""
from __future__ import annotations
import base64
import os
import time
import httpx

from pdf2md.cache import cached_call


class GeminiProvider:
    """Google Gemini provider using the generativelanguage REST API."""

    _DEFAULT_MODEL = "gemini-2.0-flash"
    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, model: str | None = None) -> None:
        self._model = model or self._DEFAULT_MODEL
        self._last_call: float = 0.0
        self._min_interval: float = 4.0  # seconds between calls (15 RPM safe)

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

    def _wait_for_rate_limit(self) -> None:
        """Wait until the minimum interval has passed since the last request."""
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def complete_sync(self, prompt: str, image: bytes | None = None) -> str:
        def _call() -> str:
            api_key = os.environ.get("GEMINI_API_KEY", "")
            url = f"{self._BASE_URL}/{self._model}:generateContent"
            payload = self._build_payload(prompt, image)

            for attempt in range(5):
                self._wait_for_rate_limit()
                response = httpx.post(
                    url, json=payload, params={"key": api_key}, timeout=120,
                )
                if response.status_code == 429:
                    # Rate limited — wait longer before next attempt
                    backoff = self._min_interval * (attempt + 2)
                    self._last_call = time.monotonic() + backoff  # push back the window
                    time.sleep(backoff)
                    continue
                response.raise_for_status()
                data = response.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]

            # All retries exhausted
            response.raise_for_status()
            return ""

        return cached_call(
            _call, prompt=prompt, model=self._model, image=image, provider=self.name,
        )

    async def complete(self, prompt: str, image: bytes | None = None) -> str:
        return self.complete_sync(prompt, image)
