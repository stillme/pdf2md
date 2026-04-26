"""Document models for pdf2md output."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class Metadata(BaseModel):
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    journal: str | None = None
    date: str | None = None
    pages: int
    language: str | None = None


class Section(BaseModel):
    level: int
    title: str
    content: str
    page: int


class Figure(BaseModel):
    id: str
    caption: str | None = None
    description: str | None = None
    image_path: str | None = None
    image_base64: str | None = None
    page: int
    confidence: float = 0.0


class FigureMention(BaseModel):
    panels: list[str] = Field(default_factory=list)
    context: str = ""


class FigureIndexEntry(BaseModel):
    figure_id: str
    label: str | None = None
    figure_number: int | None = None
    is_extended: bool = False
    page: int
    caption: str | None = None
    panels: list[str] = Field(default_factory=list)
    mentions: list[FigureMention] = Field(default_factory=list)
    markdown_anchor: str = ""
    markdown_line: int | None = None
    image_hash: str | None = None
    image_path: str | None = None
    source: str = "pdf2md"
    parse_confidence: float = 0.0


class Table(BaseModel):
    id: str
    caption: str | None = None
    markdown: str = ""
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    page: int = 0
    confidence: float = 0.0


class Equation(BaseModel):
    id: str
    latex: str
    inline: bool
    context: str | None = None
    page: int = 0


class Reference(BaseModel):
    id: str
    raw: str = ""
    authors: list[str] = Field(default_factory=list)
    title: str = ""
    journal: str | None = None
    year: str | None = None
    volume: str | None = None
    pages: str | None = None
    doi: str | None = None
    url: str | None = None
    confidence: float = 0.0


class Document(BaseModel):
    markdown: str
    metadata: Metadata
    sections: list[Section] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    figure_index: list[FigureIndexEntry] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    equations: list[Equation] = Field(default_factory=list)
    bibliography: list[Reference] = Field(default_factory=list)
    confidence: float = 0.0
    page_confidences: list[float] = Field(default_factory=list)
    engine_used: str = ""
    tier_used: str = ""
    processing_time_ms: int = 0
    warnings: list[str] = Field(default_factory=list)

    def save_markdown(self, path: str) -> None:
        Path(path).write_text(self.markdown)

    def save_figures(self, directory: str) -> None:
        import base64
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        for fig in self.figures:
            if fig.image_base64:
                img_bytes = base64.b64decode(fig.image_base64)
                (dir_path / f"{fig.id}.png").write_bytes(img_bytes)

    def save_json(self, path: str) -> None:
        Path(path).write_text(self.model_dump_json(indent=2))

    def save_figure_index(self, path: str) -> None:
        payload = {
            "schema_version": "pdf2md.figure_index.v1",
            "document": {
                "title": self.metadata.title,
                "doi": self.metadata.doi,
                "pages": self.metadata.pages,
            },
            "figures": [
                entry.model_dump(exclude_none=True)
                for entry in self.figure_index
            ],
        }
        Path(path).write_text(json.dumps(payload, indent=2))
