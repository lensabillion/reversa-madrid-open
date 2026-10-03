"""Page-aware extracted text; document roles and legal changes are not inferred."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type DocumentFormat = Literal["pdf", "text"]


class ExtractedPage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    page: int = Field(ge=1)
    text: str


class ExtractedDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    format: DocumentFormat
    pages: tuple[ExtractedPage, ...]
    warnings: tuple[str, ...]
    character_count: int = Field(ge=0)
    # PDF glyphs with no character in their font (U+0000 from pypdf), usually ligatures:
    # restored by a word guess, or replaced by a space. Each count also has a warning.
    glyphs_guessed: int = Field(ge=0)
    glyphs_unresolved: int = Field(ge=0)
