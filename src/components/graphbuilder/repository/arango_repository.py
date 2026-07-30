"""ArangoDB graph persistence — stores Graph objects into ArangoDB collections.

Receives an ArangoDBConnector via dependency injection.
Uses type-specific document collections and a single edge collection.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from arango.database import StandardDatabase

from ..models import Graph, GraphNode, GraphEdge
from .base import BaseGraphRepository

logger = logging.getLogger(__name__)

_COLLECTIONS = ["patients", "doctors", "hospitals", "diseases", "medications", "procedures"]
_EDGE_COLLECTION = "edges"

_COLLECTION_MAP: dict[str, str] = {
    "patient": "patients",
    "doctor": "doctors",
    "hospital": "hospitals",
    "disease": "diseases",
    "medication": "medications",
    "procedure": "procedures",
}


class ArangoGraphRepository(BaseGraphRepository):
    def __init__(self, connector: Any, database: str):
        self._connector = connector
        self._database_name = database

    def save(self, graph: Graph) -> Path:
        db = self._connector()
        self._ensure_collections(db)

        for node in graph.nodes:
            collection_name = _COLLECTION_MAP.get(node.file_type, "patients")
            doc = node.model_dump()
            doc["_key"] = node.id
            collection = db.collection(collection_name)
            if collection.has(node.id):
                collection.update(doc)
            else:
                collection.insert(doc)

        for edge in graph.edges:
            doc = edge.model_dump()
            doc["_key"] = f"{edge.source}_{edge.target}_{edge.relation}"
            doc["_from"] = f"{_COLLECTION_MAP.get(self._resolve_type(graph, edge.source), 'patients')}/{edge.source}"
            doc["_to"] = f"{_COLLECTION_MAP.get(self._resolve_type(graph, edge.target), 'patients')}/{edge.target}"
            edge_col = db.collection(_EDGE_COLLECTION)
            if edge_col.has(doc["_key"]):
                edge_col.update(doc)
            else:
                edge_col.insert(doc)

        logger.info(
            f"ArangoDB graph persisted — {graph.node_count} nodes, {graph.edge_count} edges"
        )
        return Path(f"arangodb://{self._database_name}")

    def load(self) -> Graph | None:
        db = self._connector()
        nodes: list[GraphNode] = []
        for col_name in _COLLECTIONS:
            if db.has_collection(col_name):
                for doc in db.collection(col_name):
                    doc.pop("_key", None)
                    doc.pop("_id", None)
                    doc.pop("_rev", None)
                    nodes.append(GraphNode(**doc))

        edges: list[GraphEdge] = []
        if db.has_collection(_EDGE_COLLECTION):
            for doc in db.collection(_EDGE_COLLECTION):
                doc.pop("_key", None)
                doc.pop("_id", None)
                doc.pop("_rev", None)
                doc.pop("_from", None)
                doc.pop("_to", None)
                edges.append(GraphEdge(**doc))

        if not nodes:
            return None
        return Graph(nodes=nodes, edges=edges)

    def exists(self) -> bool:
        try:
            db = self._connector()
            return any(db.has_collection(c) for c in _COLLECTIONS)
        except Exception:
            return False

    @staticmethod
    def _ensure_collections(db: StandardDatabase) -> None:
        for col_name in _COLLECTIONS:
            if not db.has_collection(col_name):
                db.create_collection(col_name)
                logger.info("Created document collection: %s", col_name)

        if not db.has_collection(_EDGE_COLLECTION):
            db.create_collection(_EDGE_COLLECTION, edge=True)
            logger.info("Created edge collection: %s", _EDGE_COLLECTION)

    @staticmethod
    def _resolve_type(graph: Graph, node_id: str) -> str:
        for node in graph.nodes:
            if node.id == node_id:
                return node.file_type
        return "patient"
