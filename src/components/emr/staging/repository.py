"""JSON staging repository — stores drafts as atomic JSON files under storage/emr/staging.

Mirrors JsonMetadataRepository pattern.
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .models import DraftClinicalRecord, ReviewState

logger = logging.getLogger(__name__)


class JsonStagingRepository:
    def __init__(self, staging_dir: Path):
        self._dir = Path(staging_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, DraftClinicalRecord] = {}
        self._read_all()

    def _read_all(self) -> None:
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self._index[data["record_id"]] = DraftClinicalRecord(**data)
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("Skipping corrupt %s: %s", f.name, exc)

    def save(self, record: DraftClinicalRecord) -> DraftClinicalRecord:
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self._index[record.record_id] = record
        path = self._dir / f"{record.record_id}.json"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self._dir, suffix=".tmp", delete=False
        ) as tmp:
            json.dump(record.model_dump(), tmp, indent=2, ensure_ascii=False, default=str)
            tmp_name = tmp.name
        Path(tmp_name).replace(path)
        return record

    def get(self, record_id: str) -> DraftClinicalRecord | None:
        return self._index.get(record_id)

    def list_by_state(self, state: ReviewState) -> list[DraftClinicalRecord]:
        return [r for r in self._index.values() if r.workflow_state == state]

    def list_all(self) -> list[DraftClinicalRecord]:
        return list(self._index.values())
