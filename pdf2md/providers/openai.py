"""OpenAI VLM provider using the Chat Completions API."""
from __future__ import annotations
import base64
import os
import httpx


class OpenAIProvider:
    """OpenAI GPT provider via the Chat Completions REST API."""

    _DEFAULT_MODEL = "gpt-4o"
    _BASE_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, model: str | None = None) -> None:
        self._model = model or self._DEFAULT_MODEL

    @property
    def name(self) -> str:
        return "openai"

    def _build_payload(self, prompt: str, image: bytes | None) -> dict:
        content: list[dict] = []
        if image is not None:
            encoded = base64.b64encode(image).decode("utf-8")
            from pdf2md.providers.base import detect_image_mime
            mime = detect_image_mime(image)
            data_url = f"data:{mime};base64,{encoded}"
            content.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })
        content.append({"type": "text", "text": prompt})
        return {
            "model": self._model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 4096,
        }

    def complete_sync(self, prompt: str, image: bytes | None = None) -> str:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        payload = self._build_payload(prompt, image)
        response = httpx.post(
            self._BASE_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def complete(self, prompt: str, image: bytes | None = None) -> str:
        return self.complete_sync(prompt, image)
