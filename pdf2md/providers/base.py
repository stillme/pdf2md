"""VLM provider protocol and data models."""
from __future__ import annotations
from typing import Literal, Protocol, runtime_checkable
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


VerifyStatus = Literal["pass", "fail", "error"]


class VerifyCorrection(BaseModel):
    """Structured correction patch.

    The combination of ``before_context + original + after_context`` is used
    to locate the unique replacement site in the markdown. If the contexts
    are empty (e.g. legacy ``{problem, fix}`` payloads converted at parse
    time), the patch only applies when ``original`` occurs exactly once.
    """

    region: str = ""
    before_context: str = ""  # ~30 chars before the original text
    after_context: str = ""   # ~30 chars after
    original: str             # exact text to replace
    replacement: str          # new text


class VerifyResult(BaseModel):
    status: VerifyStatus = "pass"
    confidence: float = 0.0
    corrections: list[VerifyCorrection] = Field(default_factory=list)
    explanation: str = ""


@runtime_checkable
class VLMProvider(Protocol):
    @property
    def name(self) -> str: ...
    async def complete(self, prompt: str, image: bytes | None = None) -> str: ...
    def complete_sync(self, prompt: str, image: bytes | None = None) -> str: ...
