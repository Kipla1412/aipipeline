"""Tests for the EMR pipeline — MedicalTransformer → Staging → Review → Approve.

Covers:
  1. Draft creation from transformer output
  2. Workflow state transitions
  3. Human review edits with audit trail
  4. Approval gating (only approved → FHIR)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from unittest.mock import AsyncMock, patch

import pytest

from src.components.transformers.medical_transformer import MedicalTransformer
from src.components.emr.staging.service import StagingService
from src.components.emr.staging.models import ReviewState
from src.components.emr.review.service import ReviewService


# ── Fixtures ──

@pytest.fixture
def transformer_output():
    """Simulated MedicalTransformer output (flat dict for consumers)."""
    return {
        "patient_name": "Robert Chen",
        "patient_id": "C-2026-007823",
        "doctor_name": "Dr. Anita Desai",
        "hospital": "Mercy Medical Center",
        "report_date": "2026-06-25",
        "report_type": "xray",
        "diagnoses": ["Congestive Heart Failure", "Hypertension"],
        "medications": ["Furosemide 40 mg BID", "Lisinopril 10 mg daily"],
        "procedures": [],
        "observations": [
            {"display_name": "Hemoglobin", "category": "laboratory", "value": 14.2,
             "unit": "g/dL", "reference_range": "13.5-17.5", "interpretation": "normal"},
            {"display_name": "Blood Pressure", "category": "vital_signs",
             "value": "138/84", "unit": "mmHg", "blood_pressure": {"systolic": 138.0, "diastolic": 84.0}},
        ],
        "summary": "Patient presents with CHF exacerbation.",
        "source_file": "Chest X-Ray - Robert Chen.pdf",
    }


@pytest.fixture
def staging(tmp_path, monkeypatch):
    """StagingService pointed at temp dir."""
    svc = StagingService()
    svc._repo._dir = tmp_path
    svc._repo._index = {}
    return svc


# ── Transformer layer ──

class TestMedicalTransformerLayer:
    @pytest.mark.asyncio
    async def test_transformer_produces_observations(self):
        """MedicalTransformer returns observations with numeric values."""
        llm_response = {
            "patient_name": "Robert Chen",
            "diagnoses": ["Hypertension"],
            "medications": [],
            "procedures": [],
            "observations": [
                {"category": "laboratory", "name": "Hemoglobin", "value": "14.2",
                 "unit": "g/dL", "interpretation": "normal"}
            ],
            "vitals": {"blood_pressure": "138/84"},
            "summary": "Test.",
            "sections": [],
        }
        with patch("src.components.transformers.medical_transformer.LLMClient") as mock_cls:
            mock_cls.return_value.generate = AsyncMock(return_value=json.dumps(llm_response))
            result = await MedicalTransformer({"api_key": "sk-test"}).transform("raw text")

        assert result["patient_name"] == "Robert Chen"
        assert any(o["display_name"] == "Hemoglobin" for o in result["observations"])
        assert any(o["display_name"] == "Blood Pressure" for o in result["observations"])


# ── Staging layer ──

class TestStaging:
    def test_create_draft(self, staging, transformer_output):
        draft = staging.create_draft(transformer_output, "chest.pdf")
        assert draft.workflow_state == ReviewState.DRAFT
        assert draft.reviewed_output == transformer_output
        assert draft.ai_output == transformer_output
        assert len(draft.audit_log) == 1
        assert draft.report_type == "xray"

    def test_state_transitions(self, staging, transformer_output):
        draft = staging.create_draft(transformer_output, "chest.pdf")

        draft = staging.submit_for_review(draft.record_id)
        assert draft.workflow_state == ReviewState.PENDING_REVIEW

        draft = staging.start_review(draft.record_id)
        assert draft.workflow_state == ReviewState.IN_REVIEW

        draft = staging.approve(draft.record_id, "dr_smith")
        assert draft.workflow_state == ReviewState.APPROVED

    def test_reject_path(self, staging, transformer_output):
        draft = staging.create_draft(transformer_output, "chest.pdf")
        draft = staging.reject(draft.record_id)
        assert draft.workflow_state == ReviewState.REJECTED

    def test_get_approved(self, staging, transformer_output):
        d1 = staging.create_draft(transformer_output, "a.pdf")
        d2 = staging.create_draft(transformer_output, "b.pdf")
        staging.approve(d1.record_id)

        approved = staging.get_approved()
        assert len(approved) == 1
        assert approved[0].record_id == d1.record_id


# ── Review layer ──

class TestReview:
    def test_edit_diagnosis_audited(self, staging, transformer_output):
        draft = staging.create_draft(transformer_output, "chest.pdf")
        review = ReviewService(staging)

        updated = review.edit_diagnosis(draft.record_id, 0, "Congestive Heart Failure (NYHA II)")
        assert updated.reviewed_output["diagnoses"][0] == "Congestive Heart Failure (NYHA II)"
        assert updated.workflow_state == ReviewState.IN_REVIEW

        # Audit entry records old → new
        edit_entry = [e for e in updated.audit_log if e.field == "diagnoses.0"]
        assert len(edit_entry) == 1
        assert edit_entry[0].previous_value == "Congestive Heart Failure"
        assert edit_entry[0].new_value == "Congestive Heart Failure (NYHA II)"

    def test_edit_field_audited(self, staging, transformer_output):
        draft = staging.create_draft(transformer_output, "chest.pdf")
        review = ReviewService(staging)

        updated = review.edit_field(draft.record_id, "summary", "Updated summary", "dr_smith")
        assert updated.reviewed_output["summary"] == "Updated summary"
        entry = [e for e in updated.audit_log if e.field == "summary"]
        assert entry[0].reviewer == "dr_smith"

    def test_approve_with_review(self, staging, transformer_output):
        draft = staging.create_draft(transformer_output, "chest.pdf")
        review = ReviewService(staging)

        review.edit_diagnosis(draft.record_id, 1, "Hypertension Stage II")
        approved = review.approve(draft.record_id, "dr_smith")

        assert approved.workflow_state == ReviewState.APPROVED
        state_entries = [e for e in approved.audit_log if e.field == "workflow_state"]
        assert len(state_entries) == 2  # in_review + approved transitions

    def test_reject(self, staging, transformer_output):
        draft = staging.create_draft(transformer_output, "chest.pdf")
        review = ReviewService(staging)
        rejected = review.reject(draft.record_id)
        assert rejected.workflow_state == ReviewState.REJECTED
