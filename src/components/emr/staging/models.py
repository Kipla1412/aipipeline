"""EMR Staging — workflow states, audit, draft clinical records.

Domain models for Human-in-the-Loop review with full audit trail.
Independent of FHIR and any external standard.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ReviewState(StrEnum):
    """
    Purpose:
        Enumerates the workflow states for a clinical draft record.

    Attributes:
        DRAFT: Initial state after AI extraction.
        PENDING_REVIEW: Submitted for human review.
        IN_REVIEW: Actively being reviewed.
        NEEDS_CORRECTION: Returned for edits.
        APPROVED: Final, immutable snapshot.
        REJECTED: Discarded.
    """
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    IN_REVIEW = "in_review"
    NEEDS_CORRECTION = "needs_correction"
    APPROVED = "approved"
    REJECTED = "rejected"


class AuditEntry(BaseModel):
    """
    Purpose:
        Records a single human review action on a clinical record.

    Attributes:
        timestamp: UTC ISO timestamp of the action.
        reviewer: Identity of the reviewer.
        field: The field that changed (e.g., 'diagnoses[0]').
        previous_value: Value before the change.
        new_value: Value after the change.
        reason: Human-readable reason for the change.
    """
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reviewer: str = Field(default="system")
    field: str = Field(description="Field changed, e.g. 'diagnoses[0]'")
    previous_value: Any = Field(None)
    new_value: Any = Field(None)
    reason: str | None = Field(None)


class DraftClinicalRecord(BaseModel):
    """
    Purpose:
        Represents an AI-extracted clinical draft awaiting human review.
        Tracks full audit trail and workflow state through the review lifecycle.
    """
    record_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    source_file: str = Field(default="")
    workflow_state: ReviewState = Field(default=ReviewState.DRAFT)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    report_type: str | None = None

    ai_output: dict[str, Any] = Field(default_factory=dict)
    reviewed_output: dict[str, Any] = Field(default_factory=dict)
    audit_log: list[AuditEntry] = Field(default_factory=list)
