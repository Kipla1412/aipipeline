"""Canonical in-memory Graph model for the knowledge graph layer.

GraphNode, GraphEdge, and Graph are the single source of truth
that every persistence backend consumes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    label: str
    file_type: str
    source_file: str | None = None
    source_location: None = None
    source_url: None = None
    captured_at: str | None = None
    author: None = None
    contributor: None = None
    community: None = None
    norm_label: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str
    confidence: str = "EXTRACTED"
    confidence_score: float = 1.0
    source_file: str = ""
    source_location: None = None
    weight: float = 1.0


class Graph(BaseModel):
    directed: bool = False
    multigraph: bool = False
    graph: dict[str, Any] = Field(default_factory=dict)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)
