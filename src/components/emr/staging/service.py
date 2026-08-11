"""StagingService — DraftClinicalRecord lifecycle."""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path

from .models import DraftClinicalRecord, ReviewState, AuditEntry
from .repository import JsonStagingRepository

logger = logging.getLogger(__name__)


class StagingService:
    def __init__(self, staging_dir: str = "storage/emr/staging"):
        self._repo = JsonStagingRepository(Path(staging_dir))

    def create_draft(self, ai_output: dict, source_file: str = "") -> DraftClinicalRecord:
        record = DraftClinicalRecord(
            source_file=source_file,
            ai_output=deepcopy(ai_output),
            reviewed_output=deepcopy(ai_output),
            report_type=ai_output.get("report_type"),
            audit_log=[
                AuditEntry(
                    reviewer="system",
                    field="__init__",
                    previous_value=None,
                    new_value="ai_output",
                    reason="Initial AI extraction",
                )
            ],
        )
        return self._repo.save(record)

    def get(self, record_id: str) -> DraftClinicalRecord | None:
        return self._repo.get(record_id)

    def get_pending(self) -> list[DraftClinicalRecord]:
        return self._repo.list_by_state(ReviewState.PENDING_REVIEW)

    def get_approved(self) -> list[DraftClinicalRecord]:
        return self._repo.list_by_state(ReviewState.APPROVED)

    def list_all(self) -> list[DraftClinicalRecord]:
        return self._repo.list_all()

    def submit_for_review(self, record_id: str) -> DraftClinicalRecord | None:
        return self._transition(record_id, ReviewState.PENDING_REVIEW)

    def start_review(self, record_id: str) -> DraftClinicalRecord | None:
        return self._transition(record_id, ReviewState.IN_REVIEW)

    def approve(self, record_id: str, reviewer: str = "system") -> DraftClinicalRecord | None:
        return self._transition(record_id, ReviewState.APPROVED, reviewer)

    def reject(self, record_id: str) -> DraftClinicalRecord | None:
        return self._transition(record_id, ReviewState.REJECTED)

    def request_correction(self, record_id: str) -> DraftClinicalRecord | None:
        return self._transition(record_id, ReviewState.NEEDS_CORRECTION)

    def _transition(self, record_id: str, new_state: ReviewState, reviewer: str = "system") -> DraftClinicalRecord | None:
        record = self._repo.get(record_id)
        if record is None:
            return None
        old = record.workflow_state
        record.workflow_state = new_state
        record.audit_log.append(
            AuditEntry(reviewer=reviewer, field="workflow_state",
                        previous_value=old, new_value=new_state,
                        reason=f"{old} → {new_state}")
        )
        return self._repo.save(record)
