"""Extractor protocol and data models."""

from __future__ import annotations
from typing import Protocol, runtime_checkable
from pydantic import BaseModel, Field


class RawTable(BaseModel):
    markdown: str
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    bbox: tuple[float, float, float, float] | None = None
    confidence: float = 0.5


class RawFigure(BaseModel):
    image_bytes: bytes | None = None
    caption: str | None = None
    bbox: tuple[float, float, float, float] | None = None

    class Config:
        arbitrary_types_allowed = True


class PageContent(BaseModel):
    page_number: int
    text: str = ""
    tables: list[RawTable] = Field(default_factory=list)
    figures: list[RawFigure] = Field(default_factory=list)
    confidence: float = 0.0

    class Config:
        arbitrary_types_allowed = True


class ExtractionResult(BaseModel):
    pages: list[PageContent] = Field(default_factory=list)
    engine: str = ""

    class Config:
        arbitrary_types_allowed = True


@runtime_checkable
class Extractor(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def capabilities(self) -> list[str]: ...
    def extract(self, pdf_bytes: bytes) -> ExtractionResult: ...
    def extract_page(self, pdf_bytes: bytes, page_number: int) -> PageContent: ...
