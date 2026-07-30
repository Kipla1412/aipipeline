"""Pure graph construction from MedicalDocument dicts — no persistence.

Extracted from GraphifyyEngine.build_from_documents().
Returns a Graph object. Does NOT write to disk.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from .models import Graph, GraphNode, GraphEdge

logger = logging.getLogger(__name__)


class MedicalGraphBuilder:
    """Builds a Graph from MedicalDocument dicts. Pure construction, no I/O."""

    def build(self, documents: list[dict[str, Any]], source_filename: str = "") -> Graph:
        nodes: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []

        for doc in documents:
            patient = doc.get("patient_name")
            if not patient:
                continue

            pid = self._ensure_node(nodes, patient, "patient", None)
            doctor = doc.get("doctor_name")
            hospital = doc.get("hospital")

            for diag in doc.get("diagnoses", []):
                did = self._ensure_node(nodes, diag, "disease", None)
                edges.append(self._link(pid, did, "has_disease", source_filename))

            for med in doc.get("medications", []):
                mid = self._ensure_node(nodes, med, "medication", None)
                edges.append(self._link(pid, mid, "has_medication", source_filename))

            for proc in doc.get("procedures", []):
                proc_id = self._ensure_node(nodes, proc, "procedure", None)
                edges.append(self._link(pid, proc_id, "underwent", source_filename))

            if doctor:
                did = self._ensure_node(nodes, doctor, "doctor", None)
                edges.append(self._link(pid, did, "treated_by", source_filename))

            if hospital:
                hid = self._ensure_node(nodes, hospital, "hospital", None)
                edges.append(self._link(pid, hid, "admitted_at", source_filename))
                if doctor:
                    edges.append(self._link(did, hid, "works_at", source_filename))

        graph = Graph(
            nodes=list(nodes.values()),
            edges=edges,
            metadata={
                "node_count": len(nodes),
                "edge_count": len(edges),
                "built_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info(f"Graph built — {graph.node_count} nodes, {graph.edge_count} edges")
        return graph

    def _ensure_node(
        self, nodes: dict[str, GraphNode], label: str, file_type: str, source_file: str | None
    ) -> str:
        nid = self._make_id(label)
        if nid not in nodes:
            nodes[nid] = GraphNode(
                id=nid,
                label=label,
                file_type=file_type,
                source_file=source_file,
                captured_at=datetime.now(timezone.utc).strftime("%Y-%m-%d") if source_file else None,
                norm_label=label.lower(),
            )
        return nid

    def _link(
        self, source_id: str, target_id: str, relation: str, source_filename: str
    ) -> GraphEdge:
        return GraphEdge(
            source=source_id,
            target=target_id,
            relation=relation,
            source_file=source_filename,
        )

    @staticmethod
    def _make_id(label: str) -> str:
        return hashlib.sha256(label.lower().strip().encode()).hexdigest()[:16]
