"""Document section model — preserves document layout structure."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Section(BaseModel):
    heading: str = Field(description="Section heading")
    content: str = Field(description="Section body text")
