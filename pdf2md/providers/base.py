"""VLM provider protocol and data models."""
from __future__ import annotations
from typing import Protocol, runtime_checkable
from pydantic import BaseModel, Field


def detect_image_mime(data: bytes) -> str:
    """Detect image MIME type from magic bytes."""
    if data[:4] == b'\x89PNG':
        return "image/png"
    if data[:2] == b'\xff\xd8':
        return "image/jpeg"
    if data[:4] == b'GIF8':
        return "image/gif"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    return "image/png"  # fallback


class VerifyResult(BaseModel):
    status: str  # "pass" or "fail"
    confidence: float = 0.0
    corrections: list[dict] = Field(default_factory=list)
    explanation: str = ""


@runtime_checkable
class VLMProvider(Protocol):
    @property
    def name(self) -> str: ...
    async def complete(self, prompt: str, image: bytes | None = None) -> str: ...
    def complete_sync(self, prompt: str, image: bytes | None = None) -> str: ...
