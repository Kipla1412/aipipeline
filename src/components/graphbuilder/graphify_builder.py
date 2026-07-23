"""Concrete GraphifyyBuilder — builds knowledge graphs from MedicalDocument dicts.

Wraps the self-contained GraphifyyEngine with the aiplatform component pattern
(BaseGraphBuilder ABC + Pydantic config).
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseGraphBuilder
from .schemas.graph import GraphBuilderConfig
from .engine import GraphifyyEngine

logger = logging.getLogger(__name__)


class GraphifyyBuilder(BaseGraphBuilder):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        validated = GraphBuilderConfig(**config)
        self._engine = GraphifyyEngine(validated.target_dir)
        logger.info(f"GraphifyyBuilder initialized — target_dir={validated.target_dir}")

    def build_from_documents(self, documents: List[Dict[str, Any]], source_filename: str = "") -> Path:
        logger.info(f"Building knowledge graph from {len(documents)} documents")
        graph_path = self._engine.build_from_documents(documents, source_filename)
        logger.info(f"Graph built — {graph_path}")
        return graph_path

    def tree(self, output: str = "") -> Path:
        return self._engine.tree(output)

    def cluster(self, backend: str = "", model: str = "", no_viz: bool = False) -> Path:
        return self._engine.cluster(backend=backend, model=model, no_viz=no_viz)

    def query(self, question: str, budget: int = 2000) -> str:
        return self._engine.query(question, budget)

    def explain(self, node: str) -> str:
        return self._engine.explain(node)
