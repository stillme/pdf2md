"""Gemini VLM provider using REST API."""
from __future__ import annotations
import base64
import os
import httpx


class GeminiProvider:
    """Google Gemini provider using the generativelanguage REST API."""

    _DEFAULT_MODEL = "gemini-2.0-flash"
    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, model: str | None = None) -> None:
        self._model = model or self._DEFAULT_MODEL

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
        api_key = os.environ.get("GEMINI_API_KEY", "")
        url = f"{self._BASE_URL}/{self._model}:generateContent"
        payload = self._build_payload(prompt, image)
        response = httpx.post(
            url,
            json=payload,
            params={"key": api_key},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    async def complete(self, prompt: str, image: bytes | None = None) -> str:
        return self.complete_sync(prompt, image)
