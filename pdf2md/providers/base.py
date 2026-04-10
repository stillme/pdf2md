"""VLM provider protocol and data models."""
from __future__ import annotations
from typing import Protocol, runtime_checkable
from pydantic import BaseModel, Field


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
