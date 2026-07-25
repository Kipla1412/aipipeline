"""ExtractResult — simple dataclass for extractor output."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractResult:
    markdown: str
    images: list[str | dict[str, Any]] = field(default_factory=list)
    dicom_metadata: dict[str, Any] | None = field(default=None)
    source_type: str = "pdf"  # "pdf" | "dicom"