"""Neo4j graph persistence — stores Graph objects into Neo4j using Cypher MERGE.

Receives a Neo4jConnector via dependency injection.
Uses node labels matching file_type and relationship types from graph edges.
All writes are idempotent — running multiple times never duplicates nodes/edges.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from neo4j import Driver

from ..models import Graph, GraphNode, GraphEdge
from .base import BaseGraphRepository

logger = logging.getLogger(__name__)

_NODE_LABEL_MAP: dict[str, str] = {
    "patient": "Patient",
    "doctor": "Doctor",
    "hospital": "Hospital",
    "disease": "Disease",
    "medication": "Medication",
    "procedure": "Procedure",
}

_RELATION_MAP: dict[str, str] = {
    "has_disease": "HAS_DISEASE",
    "has_medication": "TAKES_MEDICATION",
    "underwent": "UNDERWENT_PROCEDURE",
    "treated_by": "TREATED_BY",
    "admitted_at": "ADMITTED_AT",
    "works_at": "WORKS_AT",
}


class Neo4jGraphRepository(BaseGraphRepository):
    def __init__(self, connector: Any):
        self._connector = connector

    def save(self, graph: Graph) -> Path:
        driver = self._connector()
        self._ensure_constraints(driver)

        with driver.session(database=self._connector.config.database) as session:
            for node in graph.nodes:
                label = _NODE_LABEL_MAP.get(node.file_type, "Patient")
                session.run(
                    f"""
                    MERGE (n:{label} {{id: $id}})
                    SET n.label = $label,
                        n.file_type = $file_type,
                        n.norm_label = $norm_label,
                        n.source_file = $source_file,
                        n.captured_at = $captured_at,
                        n.metadata = $metadata
                    """,
                    id=node.id,
                    label=node.label,
                    file_type=node.file_type,
                    norm_label=node.norm_label,
                    source_file=node.source_file,
                    captured_at=node.captured_at,
                    metadata=json.dumps(node.metadata or {}),
                )

            for edge in graph.edges:
                relation = _RELATION_MAP.get(edge.relation, edge.relation.upper())
                source_label = _NODE_LABEL_MAP.get(
                    self._resolve_type(graph, edge.source), "Patient"
                )
                target_label = _NODE_LABEL_MAP.get(
                    self._resolve_type(graph, edge.target), "Patient"
                )
                session.run(
                    f"""
                    MATCH (a:{source_label} {{id: $source_id}})
                    MATCH (b:{target_label} {{id: $target_id}})
                    MERGE (a)-[r:{relation}]->(b)
                    SET r.confidence = $confidence,
                        r.confidence_score = $confidence_score,
                        r.source_file = $source_file,
                        r.weight = $weight
                    """,
                    source_id=edge.source,
                    target_id=edge.target,
                    confidence=edge.confidence,
                    confidence_score=edge.confidence_score,
                    source_file=edge.source_file,
                    weight=edge.weight,
                )

        logger.info(
            "Neo4j graph persisted — %d nodes, %d edges", graph.node_count, graph.edge_count
        )
        return Path(f"neo4j://{self._connector.config.uri}")

    def load(self) -> Graph | None:
        driver = self._connector()
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        with driver.session(database=self._connector.config.database) as session:
            result = session.run(
                """
                MATCH (n)
                OPTIONAL MATCH (n)-[r]->(m)
                RETURN n, r, m
                """
            )
            seen_nodes: set[str] = set()
            for record in result:
                n = record["n"]
                if n["id"] not in seen_nodes:
                    seen_nodes.add(n["id"])
                    nodes.append(
                        GraphNode(
                            id=n["id"],
                            label=n.get("label", ""),
                            file_type=n.get("file_type", ""),
                            norm_label=n.get("norm_label", ""),
                            source_file=n.get("source_file"),
                            captured_at=n.get("captured_at"),
                            metadata=json.loads(n.get("metadata", "{}")),
                        )
                    )
                r = record["r"]
                m = record["m"]
                if r is not None and m is not None:
                    edges.append(
                        GraphEdge(
                            source=n["id"],
                            target=m["id"],
                            relation=r.type.lower(),
                            confidence=r.get("confidence", "EXTRACTED"),
                            confidence_score=r.get("confidence_score", 1.0),
                            source_file=r.get("source_file", ""),
                            weight=r.get("weight", 1.0),
                        )
                    )

        if not nodes:
            return None
        return Graph(nodes=nodes, edges=edges)

    def exists(self) -> bool:
        try:
            driver = self._connector()
            with driver.session(database=self._connector.config.database) as session:
                result = session.run("MATCH (n) RETURN count(n) AS cnt")
                return result.single()["cnt"] > 0
        except Exception:
            return False

    def _ensure_constraints(self, driver: Driver) -> None:
        with driver.session(database=self._connector.config.database) as session:
            for label in _NODE_LABEL_MAP.values():
                try:
                    session.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                    )
                except Exception:
                    pass

    @staticmethod
    def _resolve_type(graph: Graph, node_id: str) -> str:
        for node in graph.nodes:
            if node.id == node_id:
                return node.file_type
        return "patient"
