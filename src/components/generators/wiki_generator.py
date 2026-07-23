"""Orchestrates patient-centric wiki page generation via the plugin registry.

WikiGenerator is completely generic — it knows NOTHING about specific
medical report types. It delegates everything to the appropriate plugin.

MedicalDocument → registry.get(report_type) → plugin.render() → wiki pages
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
import logging

from .file_manager import WikiFileManager, InvalidDocumentError, slugify
from .plugin_base import PluginRegistry, _load_plugins

logger = logging.getLogger(__name__)


class WikiGenerator:
    """
    Generic wiki page generator. No report-type knowledge whatsoever.

    Usage:
        wiki = WikiGenerator(base_dir)
        paths = wiki.generate(document, source_filename)
    """

    def __init__(self, base_dir: Path):
        self.fm = WikiFileManager(base_dir)

    def generate(self, document: dict[str, Any], source_filename: str = "") -> list[Path]:
        _load_plugins()
        start = time.monotonic()
        self.fm.ensure_readme()

        if not document.get("patient_name"):
            raise InvalidDocumentError("Document missing required field: patient_name")

        report_type = document.get("report_type")
        plugin = PluginRegistry.get(report_type)

        logger.info(f"Generating wiki for '{document.get('patient_name')}' via {plugin.report_label}")

        paths = plugin.render(document, self.fm, source_filename)

        names = {
            "patient": document.get("patient_name", "Unknown"),
            "doctor": document.get("doctor_name"),
            "hospital": document.get("hospital"),
        }
        recent = _recent_entries(names, document)
        self.fm.update_index(recent)

        page_names = list(dict.fromkeys(
            p.stem.replace("-", " ").title() for p in paths if p.suffix == ".md"
        ))
        duration = time.monotonic() - start
        self.fm.append_log(
            source_file=source_filename,
            patient=names["patient"],
            generated_pages=page_names,
            duration_s=duration,
        )

        logger.info(f"Wiki generation complete — {len(paths)} files in {duration:.2f}s")
        return paths


def _recent_entries(names: dict, doc: dict) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = [(slugify(names["patient"]), names["patient"])]
    if names["doctor"]:
        entries.append((slugify(names["doctor"]), names["doctor"]))
    for d in doc.get("diagnoses", []):
        entries.append((slugify(d), d))
    return entries
