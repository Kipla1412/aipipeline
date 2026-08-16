"""fhir-staging bridge — push Clinical Domain Model output to the staging service.

Pipeline integration:
    1. create_staging_record(file metadata + clinical context) → id (pending)
    2. patch_staging_record(id, status=completed, observations=[...])
"""

from __future__ import annotations

import logging
from typing import Any

from .client import FhirStagingClient
from .mapper import StagingObservationMapper

logger = logging.getLogger(__name__)


class StagingPushService:
    """Composes the client + mapper: file record → fhir-staging, observations → PATCH."""

    def __init__(self, base_url: str | None = None):
        self._client = FhirStagingClient(base_url)
        self._mapper = StagingObservationMapper()

    def push_document(
        self,
        *,
        file_id: str,
        filename: str,
        content_type: str | None,
        size_bytes: int | None,
        document: dict[str, Any],
        patient_id: int | None = None,
        encounter_id: int | None = None,
        service_request_id: int | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Register the document, then PATCH back the extracted observations.

        Returns the final record dict from fhir-staging (status: completed).
        """
        # 1. Register the file → pending
        create_payload: dict[str, Any] = {
            "file_id": file_id,
            "attachment_title": filename,
            "attachment_content_type": content_type,
            "attachment_size": size_bytes,
            "org_id": org_id,
            "user_id": user_id,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "service_request_id": service_request_id,
            "created_by": "aiplatform-agent",
        }
        created = self._client.create_staging_record(create_payload)
        staging_record_id = created["id"]
        logger.info("Registered staging record %s (file=%s, status=%s)",
                    staging_record_id, filename, created.get("status"))

        # 2. Map observations → fhir-staging ObservationInput shape
        observations = [
            self._mapper.map(obs)
            for obs in document.get("observations", [])
            if isinstance(obs, dict)
        ]

        # 3. PATCH back → completed
        patch_payload: dict[str, Any] = {
            "status": "completed",
            "updated_by": "aiplatform-agent",
            "observations": observations,
        }
        if observations:
            from datetime import datetime, timezone
            patch_payload["processed_at"] = datetime.now(timezone.utc).isoformat()

        updated = self._client.patch_staging_record(staging_record_id, patch_payload)
        logger.info("Staged %d observations on record %s (status=%s)",
                    len(observations), staging_record_id, updated.get("status"))
        return updated

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> StagingPushService:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
