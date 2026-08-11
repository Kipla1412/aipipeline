"""FHIR Repository — write Bundles to JSON files.

ABC for future HAPI/Azure/GCP backends.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class IFHIRRepository(ABC):
    @abstractmethod
    def save(self, bundle, record_id: str) -> Path: ...


class LocalFHIRRepository(IFHIRRepository):
    def __init__(self, output_dir: str = "storage/emr/fhir"):
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, bundle, record_id: str) -> Path:
        path = self._dir / f"{record_id}.json"
        data = bundle.model_dump() if hasattr(bundle, "model_dump") else bundle
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        logger.info("FHIR Bundle → %s (%d entries)", path, len(data.get("entry", [])))
        return path
