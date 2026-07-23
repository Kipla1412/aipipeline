"""ExtractResult — simple dataclass for extractor output."""

from dataclasses import dataclass, field


@dataclass
class ExtractResult:
    markdown: str
    images: list[str] = field(default_factory=list)
