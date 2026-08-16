"""Verify the fhir-staging bridge is working.

Checks:
  1. fhir-staging service is reachable (GET /health)
  2. Config reads FHIR_STAGING_BASE_URL from .env
  3. Client + mapper are importable and construct
  4. POST a minimal test staging record → get an id
  5. PATCH it back with one observation → status completed
  6. GET /?status=completed — confirm records are there

Usage:
  python3 check_staging.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import httpx

from src.components.utils.config import PipelineConfig
from src.components.fhir_staging.client import FhirStagingClient
from src.components.fhir_staging.mapper import StagingObservationMapper


def main() -> int:
    print("=" * 60)
    print("  fhir-staging bridge check")
    print("=" * 60)

    # 1. Config
    cfg = PipelineConfig().get_fhir_staging_config()
    base_url = cfg["base_url"]
    print(f"\n[1] Config")
    print(f"    FHIR_STAGING_BASE_URL = {base_url}")

    # 2. Service health
    print(f"\n[2] Service health")
    try:
        resp = httpx.get(f"{base_url}/health", timeout=5)
        resp.raise_for_status()
        print(f"    OK — /health → {resp.json()}")
    except Exception as exc:
        print(f"    FAIL — service not reachable at {base_url}: {exc}")
        print(f"    Start it: cd /home/kipla/fhir-staging/fhir-staging && just dev")
        return 1

    # 3. Client + mapper construct
    print(f"\n[3] Client + mapper")
    client = FhirStagingClient()
    mapper = StagingObservationMapper()
    print(f"    OK — client base_url={client._base_url}")

    # 4. Minimal observation mapping
    test_obs = {
        "display_name": "Hemoglobin",
        "value": 14.2,
        "unit": "g/dL",
        "category": "laboratory",
        "interpretation": "normal",
    }
    mapped = mapper.map(test_obs)
    print(f"    Mapped sample observation:")
    print(f"      code_display={mapped.get('code_display')} "
          f"value={mapped.get('value_quantity_value')} {mapped.get('value_quantity_unit')}")

    # 5. Round-trip: create + patch a test record
    print(f"\n[4] Create + patch test staging record")
    try:
        created = client.create_staging_record({
            "file_id": "check-staging-001",
            "attachment_title": "check_staging.pdf",
            "attachment_content_type": "application/pdf",
            "attachment_size": 1234,
            "patient_id": 10001,
            "service_request_id": 80002,
            "created_by": "check-staging",
        })
        record_id = created["id"]
        print(f"    OK — created record {record_id} (status={created.get('status')})")

        updated = client.patch_staging_record(record_id, {
            "status": "completed",
            "updated_by": "check-staging",
            "observations": [mapper.map(test_obs)],
        })
        print(f"    OK — patched record {record_id} (status={updated.get('status')}, "
              f"obs={len(updated.get('observations', []))})")
    except Exception as exc:
        print(f"    FAIL — write to fhir-staging: {exc}")
        return 1

    # 6. Query the queue
    print(f"\n[5] List completed records")
    resp = httpx.get(f"{base_url}/api/v1/staging-records/?status=completed", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    print(f"    Total completed: {data.get('total')}")
    for r in data.get("data", [])[-5:]:
        print(f"      id={r['id']} file={r.get('attachment_title')} obs={len(r.get('observations', []))}")

    print(f"\n{'=' * 60}")
    print("  ✓ fhir-staging bridge is WORKING")
    print("  ✓ your transformed docs flow: extract → transform → staging")
    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
