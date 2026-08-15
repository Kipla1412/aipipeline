"""Human Review Service — edit clinical fields, approve/reject with full audit."""

from __future__ import annotations

import logging
from copy import deepcopy

from ..staging.models import DraftClinicalRecord, ReviewState, AuditEntry
from ..staging.service import StagingService

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, staging: StagingService):
        """
        Purpose:
            Initializes ReviewService over an existing StagingService.

        Args:
            staging: The StagingService used to load/save draft records.
        """
        self._staging = staging

    def edit_field(
        self, record_id: str, field: str, new_value: object, reviewer: str = "reviewer",
        reason: str | None = None,
    ) -> DraftClinicalRecord | None:
        """
        Purpose:
            Edits a field in reviewed_output, logs an audit entry, and
            transitions the record to IN_REVIEW.

        Args:
            record_id: The record to edit.
            field: Dot-path of the field (e.g. 'diagnoses.0', 'summary').
            new_value: The replacement value.
            reviewer: Identity of the reviewer.
            reason: Optional human-readable reason for the change.

        Returns:
            DraftClinicalRecord | None: Updated record or None if not found.
        """
        record = self._staging.get(record_id)
        if record is None:
            return None
        old = self._get_at(record.reviewed_output, field)
        self._set_at(record.reviewed_output, field, deepcopy(new_value))
        record.audit_log.append(
            AuditEntry(reviewer=reviewer, field=field, previous_value=old,
                        new_value=new_value, reason=reason)
        )
        if record.workflow_state == ReviewState.DRAFT:
            record.workflow_state = ReviewState.IN_REVIEW
        return self._staging._repo.save(record)

    def edit_diagnosis(
        self, record_id: str, index: int, name: str, reviewer: str = "reviewer"
    ) -> DraftClinicalRecord | None:
        """
        Purpose:
            Edits a diagnosis at the given index, auditing old→new values.

        Args:
            record_id: The record to edit.
            index: Index into the diagnoses list.
            name: New diagnosis string.
            reviewer: Identity of the reviewer.

        Returns:
            DraftClinicalRecord | None: Updated record or None if not found.
        """
        return self.edit_field(record_id, f"diagnoses.{index}", name, reviewer)

    def edit_observation(
        self, record_id: str, display_name: str, *, value: object = None,
        unit: str = None, interpretation: str = None, reviewer: str = "reviewer",
    ) -> DraftClinicalRecord | None:
        """
        Purpose:
            Edits value/unit/interpretation of the first matching observation.

        Args:
            record_id: The record to edit.
            display_name: Display name to match in observations list.
            value: New value (if provided).
            unit: New unit (if provided).
            interpretation: New interpretation (if provided).
            reviewer: Identity of the reviewer.

        Returns:
            DraftClinicalRecord | None: Updated record or None if not found.
        """
        record = self._staging.get(record_id)
        if record is None:
            return None
        observations = record.reviewed_output.get("observations", [])
        for i, obs in enumerate(observations):
            if isinstance(obs, dict) and obs.get("display_name") == display_name:
                return self.edit_field(record_id, f"observations.{i}.{display_name}",
                                        {"value": value, "unit": unit, "interpretation": interpretation},
                                        reviewer)
        return record

    def approve(self, record_id: str, reviewer: str = "reviewer") -> DraftClinicalRecord | None:
        """
        Purpose:
            Starts review then approves the record (IN_REVIEW → APPROVED).

        Args:
            record_id: The record to approve.
            reviewer: Identity of the reviewer.

        Returns:
            DraftClinicalRecord | None: Approved record or None if not found.
        """
        self._staging.start_review(record_id)
        return self._staging.approve(record_id, reviewer)

    def reject(self, record_id: str) -> DraftClinicalRecord | None:
        """
        Purpose:
            Rejects a record (transitions to REJECTED).

        Args:
            record_id: The record to reject.

        Returns:
            DraftClinicalRecord | None: Rejected record or None if not found.
        """
        return self._staging.reject(record_id)

    @staticmethod
    def _get_at(data: dict, field: str) -> object:
        """
        Purpose:
            Reads a dot-path value from a nested dict/list.

        Args:
            data: The nested structure.
            field: Dot-path (e.g. 'observations.0.value').

        Returns:
            object: Value at the path, or None if not found.
        """
        parts = field.split(".")
        cur = data
        for p in parts:
            if isinstance(cur, dict):
                cur = cur.get(p)
            elif isinstance(cur, list):
                try: cur = cur[int(p)]
                except: return None
            else: return None
        return cur

    @staticmethod
    def _set_at(data: dict, field: str, value: object) -> None:
        """
        Purpose:
            Writes a value at a dot-path in a nested dict/list in-place.

        Args:
            data: The nested structure to mutate.
            field: Dot-path (e.g. 'diagnoses.0').
            value: The value to set.
        """
        parts = field.split(".")
        cur = data
        for p in parts[:-1]:
            if isinstance(cur, list):
                try:
                    cur = cur[int(p)]
                except (ValueError, IndexError):
                    return
            else:
                if p not in cur:
                    cur[p] = {}
                cur = cur[p]
        if isinstance(cur, list):
            try:
                cur[int(parts[-1])] = value
            except (ValueError, IndexError):
                pass
        else:
            cur[parts[-1]] = value
