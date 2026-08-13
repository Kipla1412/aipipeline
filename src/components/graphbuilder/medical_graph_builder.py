"""Pure graph construction from MedicalDocument dicts — no persistence.

Extracted from GraphifyyEngine.build_from_documents().
Returns a Graph object. Does NOT write to disk.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

from .models import Graph, GraphNode, GraphEdge

logger = logging.getLogger(__name__)

_REPORT_TYPE_DIR: dict[str, str] = {
    "mri": "MRI", "ct": "CT", "xray": "X-Ray", "ultrasound": "Ultrasound",
    "ecg": "ECG", "blood_report": "Blood", "lab_report": "LabReports",
    "prescription": "Prescription", "discharge_summary": "DischargeSummary",
    "consultation": "Consultation", "operative_report": "OperativeReports",
    "histopathology": "Pathology", "microbiology": "Microbiology", "other": "Other",
}


class MedicalGraphBuilder:
    """Builds a Graph from MedicalDocument dicts. Pure construction, no I/O."""

    def build(self, documents: list[dict[str, Any]], source_filename: str = "") -> Graph:
        """
        Purpose:
            Builds an in-memory Graph from MedicalDocument dicts. No persistence.

        Args:
            documents: List of MedicalDocument dicts.
            source_filename: Original source file reference.

        Returns:
            Graph: In-memory Graph model with nodes and edges.
        """
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

            # Report node
            doc_id = doc.get("document_id", "")
            if doc_id:
                rid = self._make_id(doc_id)
                report_type = doc.get("report_type", "other")
                report_date = doc.get("report_date", "")
                wiki_path = self._build_report_path(
                    patient, doc_id, report_type, doc.get("source_filename", "")
                )
                nodes[rid] = GraphNode(
                    id=rid,
                    label=doc_id,
                    file_type="report",
                    source_file=wiki_path,
                    captured_at=report_date,
                    norm_label=doc_id.lower(),
                    metadata={
                        "report_type": report_type,
                        "report_date": report_date,
                        "source_filename": doc.get("source_filename", ""),
                    },
                )
                edges.append(self._link(pid, rid, "has_report", source_filename))
                if doctor:
                    edges.append(self._link(rid, did, "generated_by", source_filename))
                if hospital:
                    edges.append(self._link(rid, hid, "generated_at", source_filename))

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
        """
        Purpose:
            Returns existing node ID or creates a new node for a label.

        Returns:
            str: Node ID (SHA-256 hash).
        """
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
        """
        Purpose:
            Creates a GraphEdge connecting two node IDs.

        Returns:
            GraphEdge: Edge with relation type and source reference.
        """
        return GraphEdge(
            source=source_id,
            target=target_id,
            relation=relation,
            source_file=source_filename,
        )

    @staticmethod
    def _make_id(label: str) -> str:
        """Generate a 16-char hex node ID from label via SHA-256."""
        return hashlib.sha256(label.lower().strip().encode()).hexdigest()[:16]

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to lowercase kebab-case slug."""
        return re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")

    @classmethod
    def _build_report_path(
        cls, patient_name: str, document_id: str, report_type: str, source_filename: str
    ) -> str:
        """Build the wiki-style report page path from document metadata."""
        patient_slug = cls._slugify(patient_name)
        report_name = document_id.rsplit(":", 1)[0] if ":" in document_id else source_filename.rsplit(".", 1)[0] if source_filename else document_id
        report_slug = cls._slugify(report_name)
        report_dir = _REPORT_TYPE_DIR.get(report_type.lower(), "Other")
        return f"Patients/{patient_slug}/Reports/{report_dir}/{report_slug}.md"
