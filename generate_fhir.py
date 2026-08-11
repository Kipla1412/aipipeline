"""FHIR generation CLI — convert approved records to FHIR R4 Bundles.

Usage:
  python3 generate_fhir.py <record_id>          # single approved record
  python3 generate_fhir.py --all-approved        # batch all
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.components.emr.staging.service import StagingService
from src.components.emr.fhir.bundle_builder import BundleBuilder
from src.components.emr.repository.fhir_repository import LocalFHIRRepository


def generate(record_id: str) -> dict | None:
    staging = StagingService()
    draft = staging.get(record_id)
    if draft is None:
        print(f"Not found: {record_id}")
        return None
    if draft.workflow_state != "approved":
        print(f"Not approved (state={draft.workflow_state})")
        return None

    bundle = BundleBuilder().build(draft.reviewed_output)
    repo = LocalFHIRRepository()
    path = repo.save(bundle, record_id)
    print(f"FHIR Bundle: {len(bundle.entry)} resources → {path}")
    return bundle.model_dump()


def generate_all():
    staging = StagingService()
    approved = staging.get_approved()
    print(f"Found {len(approved)} approved record(s)")
    for draft in approved:
        bundle = BundleBuilder().build(draft.reviewed_output)
        repo = LocalFHIRRepository()
        repo.save(bundle, draft.record_id)
        print(f"  {draft.record_id}: {len(bundle.entry)} resources")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--all-approved" in sys.argv:
        generate_all()
    elif args:
        bundle = generate(args[0])
        if bundle:
            print(json.dumps(bundle, indent=2, ensure_ascii=False, default=str))
    else:
        print("Usage: python3 generate_fhir.py <record_id>  or  --all-approved")
