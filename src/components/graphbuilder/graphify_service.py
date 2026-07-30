"""Graphify CLI service — wraps graphifyy subprocess for visualization and querying.

Extracted from GraphifyyEngine.tree(), .cluster(), .query(), .explain().
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class GraphifyService:
    def __init__(self, graph_json_path: Path, target_dir: Path):
        self.graph_path = Path(graph_json_path)
        self.target_dir = Path(target_dir)
        self.out_dir = self.target_dir / "graphify-out"

    def tree(self, output: str = "") -> Path:
        out_path = Path(output) if output else (self.out_dir / "GRAPH_TREE.html")
        cmd = [
            sys.executable, "-m", "graphify", "tree",
            "--graph", str(self.graph_path), "--output", str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"graphify tree failed: {result.stderr}")
        else:
            logger.info(f"Graph tree → {out_path}")
        return out_path

    def cluster(self, backend: str = "", model: str = "", no_viz: bool = False) -> Path:
        if not self.graph_path.exists():
            raise FileNotFoundError(
                f"graph.json not found in {self.graph_path.parent} — run build() first"
            )
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
        result = subprocess.run(
            [
                sys.executable, "-m", "graphify", "query", question,
                "--graph", str(self.graph_path), "--budget", str(budget),
            ],
            capture_output=True, text=True,
        )
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"

    def explain(self, node: str) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "graphify", "explain", node, "--graph", str(self.graph_path)],
            capture_output=True, text=True,
        )
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"
