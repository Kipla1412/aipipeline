"""Repository abstraction for graph persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from ..models import Graph


class BaseGraphRepository(ABC):
    @abstractmethod
    def save(self, graph: Graph) -> Path: ...

    @abstractmethod
    def load(self) -> Graph | None: ...

    @abstractmethod
    def exists(self) -> bool: ...
