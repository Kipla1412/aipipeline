"""JSON-backed graph persistence — writes graph.json and graphify-out/graph.json.

Extracted from GraphifyyEngine._write_graph().
Produces identical output to the original implementation.
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from pathlib import Path

from .base import BaseGraphRepository
from ..models import Graph, GraphNode, GraphEdge

logger = logging.getLogger(__name__)


class JsonGraphRepository(BaseGraphRepository):
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.graph_file = self.output_dir / "graph.json"
        self._duplicate_dir = self.output_dir / "graphify-out"
        self._duplicate_file = self._duplicate_dir / "graph.json"

    def save(self, graph: Graph) -> Path:
        payload = self._serialize(graph)
        json_text = json.dumps(payload, indent=2, ensure_ascii=False)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.graph_file.write_text(json_text, encoding="utf-8")

        self._duplicate_dir.mkdir(exist_ok=True)
        self._duplicate_file.write_text(json_text, encoding="utf-8")

        logger.info(
            f"Graph persisted — {graph.node_count} nodes, {graph.edge_count} edges → {self.graph_file}"
        )
        return self.graph_file

    def load(self) -> Graph | None:
        if not self.graph_file.exists():
            return None
        data = json.loads(self.graph_file.read_text(encoding="utf-8"))
        nodes = [GraphNode(**n) for n in data.get("nodes", [])]
        edges = [GraphEdge(**e) for e in data.get("links", [])]
        return Graph(nodes=nodes, edges=edges)

    def exists(self) -> bool:
        return self.graph_file.exists()

    @staticmethod
    def _serialize(graph: Graph) -> OrderedDict:
        return OrderedDict([
            ("directed", graph.directed),
            ("multigraph", graph.multigraph),
            ("graph", graph.graph),
            ("nodes", [JsonGraphRepository._serialize_node(n) for n in graph.nodes]),
            ("links", [JsonGraphRepository._serialize_edge(e) for e in graph.edges]),
        ])

    @staticmethod
    def _serialize_node(node: GraphNode) -> OrderedDict:
        return OrderedDict([
            ("label", node.label),
            ("file_type", node.file_type),
            ("source_file", node.source_file),
            ("source_location", node.source_location),
            ("source_url", node.source_url),
            ("captured_at", node.captured_at),
            ("author", node.author),
            ("contributor", node.contributor),
            ("community", node.community),
            ("norm_label", node.norm_label),
            ("id", node.id),
        ])

    @staticmethod
    def _serialize_edge(edge: GraphEdge) -> OrderedDict:
        return OrderedDict([
            ("relation", edge.relation),
            ("confidence", edge.confidence),
            ("confidence_score", edge.confidence_score),
            ("source_file", edge.source_file),
            ("source_location", edge.source_location),
            ("weight", edge.weight),
            ("source", edge.source),
            ("target", edge.target),
        ])
