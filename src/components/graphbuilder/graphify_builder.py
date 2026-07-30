"""GraphifyyBuilder — facade composing graph construction, persistence, and CLI operations.

Maintains identical public API to the original GraphifyyBuilder for
backward compatibility. Internally delegates to:
  - MedicalGraphBuilder  (pure construction)
  - JsonGraphRepository  (JSON persistence)
  - GraphifyService      (CLI operations)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base import BaseGraphBuilder
from .schemas.graph import GraphBuilderConfig
from .medical_graph_builder import MedicalGraphBuilder
from .repository.json_repository import JsonGraphRepository
from .graphify_service import GraphifyService

logger = logging.getLogger(__name__)


class GraphifyyBuilder(BaseGraphBuilder):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        validated = GraphBuilderConfig(**config)
        target = Path(validated.target_dir)
        self._builder = MedicalGraphBuilder()
        self._repo = JsonGraphRepository(target)
        self._service = GraphifyService(
            graph_json_path=target / "graphify-out" / "graph.json",
            target_dir=target,
        )
        logger.info(f"GraphifyyBuilder initialized — target_dir={target}")

    def build_from_documents(
        self, documents: list[dict[str, Any]], source_filename: str = ""
    ) -> Path:
        logger.info(f"Building knowledge graph from {len(documents)} documents")
        graph = self._builder.build(documents, source_filename)
        graph_path = self._repo.save(graph)
        logger.info(f"Graph built — {graph_path}")
        return graph_path

    def tree(self, output: str = "") -> Path:
        return self._service.tree(output)

    def cluster(self, backend: str = "", model: str = "", no_viz: bool = False) -> Path:
        return self._service.cluster(backend=backend, model=model, no_viz=no_viz)

    def query(self, question: str, budget: int = 2000) -> str:
        return self._service.query(question, budget)

    def explain(self, node: str) -> str:
        return self._service.explain(node)
