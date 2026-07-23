"""
GraphBuilder — independent knowledge graph builder and graphifyy CLI integration.

Primary path: build_from_documents(docs) — consume MedicalDocument dicts directly.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GraphifyyEngine:
    """Independent graph layer."""

    def __init__(self, target_dir: str = "storage/wiki"):
        self.target_dir = Path(target_dir).resolve()
        self.graph_file = self.target_dir / "graph.json"
        self.out_dir = self.target_dir / "graphify-out"
        self.target_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Graphifyy Engine initialized — target: {self.target_dir}")

    def build_from_documents(self, documents: list[dict[str, Any]], source_filename: str = "") -> Path:
        """Primary path: build graph directly from MedicalDocument dicts. No markdown parsing."""
        nodes: dict[str, dict] = {}
        links: list[dict] = []

        for doc in documents:
            patient = doc.get("patient_name")
            if not patient:
                continue

            pid = self._ensure_node(nodes, patient, "patient", None)
            doctor = doc.get("doctor_name")
            hospital = doc.get("hospital")

            for diag in doc.get("diagnoses", []):
                did = self._ensure_node(nodes, diag, "disease", None)
                links.append(self._link(pid, did, "has_disease", source_filename))

            for med in doc.get("medications", []):
                mid = self._ensure_node(nodes, med, "medication", None)
                links.append(self._link(pid, mid, "has_medication", source_filename))

            for proc in doc.get("procedures", []):
                proc_id = self._ensure_node(nodes, proc, "procedure", None)
                links.append(self._link(pid, proc_id, "underwent", source_filename))

            if doctor:
                did = self._ensure_node(nodes, doctor, "doctor", None)
                links.append(self._link(pid, did, "treated_by", source_filename))

            if hospital:
                hid = self._ensure_node(nodes, hospital, "hospital", None)
                links.append(self._link(pid, hid, "admitted_at", source_filename))
                if doctor:
                    links.append(self._link(did, hid, "works_at", source_filename))

        return self._write_graph(nodes, links)

    def tree(self, output: str = "") -> Path:
        out_path = Path(output) if output else (self.out_dir / "GRAPH_TREE.html")
        cmd = [sys.executable, "-m", "graphify", "tree",
               "--graph", str(self.out_dir / "graph.json"), "--output", str(out_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"graphify tree failed: {result.stderr}")
        else:
            logger.info(f"Graph tree → {out_path}")
        return out_path

    def cluster(self, backend: str = "", model: str = "", no_viz: bool = False) -> Path:
        if not (self.out_dir / "graph.json").exists():
            raise FileNotFoundError(f"graph.json not found in {self.out_dir} — run build() first")
        cmd = [sys.executable, "-m", "graphify", "cluster-only", str(self.target_dir)]
        if no_viz:
            cmd.append("--no-viz")
        if backend:
            cmd.extend(["--backend", backend])
        if model:
            cmd.extend(["--model", model])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        return self.out_dir

    def query(self, question: str, budget: int = 2000) -> str:
        result = subprocess.run([sys.executable, "-m", "graphify", "query", question,
                "--graph", str(self.out_dir / "graph.json"), "--budget", str(budget)],
                capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"

    def explain(self, node: str) -> str:
        result = subprocess.run([sys.executable, "-m", "graphify", "explain", node,
                "--graph", str(self.out_dir / "graph.json")], capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"

    def _ensure_node(self, nodes: dict, label: str, file_type: str, source_file: str | None) -> str:
        nid = self._make_id(label)
        if nid not in nodes:
            nodes[nid] = {
                "label": label, "file_type": file_type, "source_file": source_file,
                "source_location": None, "source_url": None,
                "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%d") if source_file else None,
                "author": None, "contributor": None, "community": None,
                "norm_label": label.lower(), "id": nid,
            }
        return nid

    def _link(self, source_id: str, target_id: str, relation: str, source_filename: str) -> dict:
        return {
            "relation": relation, "confidence": "EXTRACTED",
            "confidence_score": 1.0, "source_file": source_filename,
            "source_location": None, "weight": 1.0,
            "source": source_id, "target": target_id,
        }

    def _write_graph(self, nodes: dict, links: list) -> Path:
        graph = {
            "directed": False, "multigraph": False, "graph": {},
            "nodes": list(nodes.values()), "links": links,
        }
        self.graph_file.write_text(json.dumps(graph, indent=2), encoding="utf-8")
        self.out_dir.mkdir(exist_ok=True)
        (self.out_dir / "graph.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
        logger.info(f"Graph built — {len(nodes)} nodes, {len(links)} links → {self.graph_file}")
        return self.graph_file

    @staticmethod
    def _make_id(label: str) -> str:
        return hashlib.sha256(label.lower().strip().encode()).hexdigest()[:16]
