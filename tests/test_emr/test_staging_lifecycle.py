"""Simple lifecycle test for the staging/approved workflow.

Verifies: create_draft → submit_for_review → approve,
asserting state transitions, audit-trail entries (old→new, reviewer),
and approval gating (only APPROVED records appear in get_approved).

Distinct from the mock-based transformer test; uses a real in-memory
StagingService pointed at a temp directory.
"""

import sys
from pathlib import Path
from copy import deepcopy

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from src.components.emr.staging.service import StagingService
from src.components.emr.staging.models import ReviewState


@pytest.fixture
def sample_doc():
    return {
        "patient_name": "Jane Doe",
        "report_type": "ct",
        "diagnoses": ["Pneumonia"],
        "medications": ["Amoxicillin"],
        "observations": [
            {"display_name": "Hemoglobin", "value": 14.2, "unit": "g/dL"},
            {"display_name": "Blood Pressure", "value": {"systolic": 120.0, "diastolic": 80.0}},
        ],
    }


@pytest.fixture
def staging(tmp_path):
    svc = StagingService()
    svc._repo._dir = tmp_path
    svc._repo._index = {}
    return svc


def test_draft_to_approved_lifecycle(staging, sample_doc):
    # 1. Create draft
    draft = staging.create_draft(deepcopy(sample_doc), "scan.pdf")
    assert draft.workflow_state == ReviewState.DRAFT
    assert len(draft.audit_log) == 1

    # 2. Submit for review
    draft = staging.submit_for_review(draft.record_id)
    assert draft.workflow_state == ReviewState.PENDING_REVIEW

    # 3. Start review
    draft = staging.start_review(draft.record_id)
    assert draft.workflow_state == ReviewState.IN_REVIEW

    # 4. Approve
    draft = staging.approve(draft.record_id, reviewer="dr_smith")
    assert draft.workflow_state == ReviewState.APPROVED

    # Audit trail captures every state transition with reviewer identity
    state_entries = [e for e in draft.audit_log if e.field == "workflow_state"]
    assert len(state_entries) == 3  # pending → in_review → approved
    assert state_entries[-1].new_value == ReviewState.APPROVED
    assert state_entries[-1].reviewer == "dr_smith"

    # 5. Approval gating: only approved records surface
    assert staging.get_approved()[0].record_id == draft.record_id
    assert staging.get_pending() == []
