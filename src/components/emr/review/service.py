"""Human Review Service — edit clinical fields, approve/reject with full audit."""

from __future__ import annotations

import logging
from copy import deepcopy

from ..staging.models import DraftClinicalRecord, ReviewState, AuditEntry
from ..staging.service import StagingService

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, staging: StagingService):
        self._staging = staging

    def edit_field(
        self, record_id: str, field: str, new_value: object, reviewer: str = "reviewer",
        reason: str | None = None,
    ) -> DraftClinicalRecord | None:
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
        return self.edit_field(record_id, f"diagnoses.{index}", name, reviewer)

    def edit_observation(
        self, record_id: str, display_name: str, *, value: object = None,
        unit: str = None, interpretation: str = None, reviewer: str = "reviewer",
    ) -> DraftClinicalRecord | None:
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
        self._staging.start_review(record_id)
        return self._staging.approve(record_id, reviewer)

    def reject(self, record_id: str) -> DraftClinicalRecord | None:
        return self._staging.reject(record_id)

    @staticmethod
    def _get_at(data: dict, field: str) -> object:
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
