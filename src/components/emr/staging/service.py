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
        """
        Purpose:
            Initializes StagingService with a JSON staging repository.

        Args:
            staging_dir: Directory where draft clinical records are persisted.
        """
        self._repo = JsonStagingRepository(Path(staging_dir))

    def create_draft(self, ai_output: dict, source_file: str = "") -> DraftClinicalRecord:
        """
        Purpose:
            Creates a DraftClinicalRecord in DRAFT state from AI output.

        Args:
            ai_output: Transformed Clinical Domain Model dict.
            source_file: Original source filename.

        Returns:
            DraftClinicalRecord: The created draft record.
        """
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
        """
        Purpose:
            Retrieves a draft record by ID.

        Args:
            record_id: The record UUID (hex prefix).

        Returns:
            DraftClinicalRecord | None: Record if found, else None.
        """
        return self._repo.get(record_id)

    def get_pending(self) -> list[DraftClinicalRecord]:
        """
        Purpose:
            Lists records in PENDING_REVIEW state.

        Returns:
            list: Draft records awaiting review.
        """
        return self._repo.list_by_state(ReviewState.PENDING_REVIEW)

    def get_approved(self) -> list[DraftClinicalRecord]:
        """
        Purpose:
            Lists records in APPROVED state.

        Returns:
            list: Approved draft records.
        """
        return self._repo.list_by_state(ReviewState.APPROVED)

    def list_all(self) -> list[DraftClinicalRecord]:
        """
        Purpose:
            Lists all staged records regardless of state.

        Returns:
            list: All DraftClinicalRecord objects.
        """
        return self._repo.list_all()

    def submit_for_review(self, record_id: str) -> DraftClinicalRecord | None:
        """
        Purpose:
            Transitions a record from DRAFT to PENDING_REVIEW.

        Returns:
            DraftClinicalRecord | None: Updated record or None if not found.
        """
        return self._transition(record_id, ReviewState.PENDING_REVIEW)

    def start_review(self, record_id: str) -> DraftClinicalRecord | None:
        """
        Purpose:
            Transitions a record from PENDING_REVIEW to IN_REVIEW.

        Returns:
            DraftClinicalRecord | None: Updated record or None if not found.
        """
        return self._transition(record_id, ReviewState.IN_REVIEW)

    def approve(self, record_id: str, reviewer: str = "system") -> DraftClinicalRecord | None:
        """
        Purpose:
            Approves a record, transitioning it to APPROVED state.

        Args:
            record_id: The record to approve.
            reviewer: Name of the reviewer.

        Returns:
            DraftClinicalRecord | None: Approved record or None if not found.
        """
        return self._transition(record_id, ReviewState.APPROVED, reviewer)

    def reject(self, record_id: str) -> DraftClinicalRecord | None:
        """
        Purpose:
            Rejects a record, transitioning it to REJECTED state.

        Returns:
            DraftClinicalRecord | None: Rejected record or None if not found.
        """
        return self._transition(record_id, ReviewState.REJECTED)

    def request_correction(self, record_id: str) -> DraftClinicalRecord | None:
        """
        Purpose:
            Requests correction, transitioning to NEEDS_CORRECTION.

        Returns:
            DraftClinicalRecord | None: Updated record or None if not found.
        """
        return self._transition(record_id, ReviewState.NEEDS_CORRECTION)

    def _transition(self, record_id: str, new_state: ReviewState, reviewer: str = "system") -> DraftClinicalRecord | None:
        """
        Purpose:
            Internal: sets a new workflow state and appends an audit entry.

        Args:
            record_id: The record to transition.
            new_state: Target ReviewState.
            reviewer: Identity of the reviewer.

        Returns:
            DraftClinicalRecord | None: Updated record or None if not found.
        """
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
