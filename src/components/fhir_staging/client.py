"""HTTP client for the fhir-staging service (colleague's FastAPI app).

Endpoints (all /api/v1/staging-records):
    POST   /              register a document → status: pending
    PATCH  /{id}          write back extracted observations + status

Plain snake_case JSON, no auth. Base URL comes from PipelineConfig
(FHIR_STAGING_BASE_URL env / .env) unless overridden explicitly.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..utils.config import PipelineConfig

logger = logging.getLogger(__name__)


class FhirStagingClient:
    """Single responsibility: talk to the fhir-staging HTTP API."""

    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        config = PipelineConfig().get_fhir_staging_config()
        self._base_url = (base_url or config["base_url"]).rstrip("/")
        self._client = httpx.Client(timeout=timeout or config["timeout"])

    def list_pending_records(self) -> list[dict[str, Any]]:
        """Get staging records waiting for processing."""
        resp = self._client.get(
            f"{self._base_url}/api/v1/staging-records/",
            params={"status": "pending"},
        )
        resp.raise_for_status()

        data = resp.json()

        # The API returns:
        # {
        #     "total": 1,
        #     "limit": 20,
        #     "offset": 0,
        #     "data": [...]
        # }
        return data.get("data", [])


    def get_staging_record(self, staging_record_id: int) -> dict[str, Any]:
        """Get one staging record by public staging_record_id."""
        resp = self._client.get(
            f"{self._base_url}/api/v1/staging-records/{staging_record_id}"
        )
        resp.raise_for_status()
        return resp.json()


    def update_status(
        self,
        staging_record_id: int,
        status: str,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        """Update the workflow status of an existing staging record."""
        payload: dict[str, Any] = {
            "status": status,
            "updated_by": "aiplatform-agent",
        }

        if error_message:
            payload["error_message"] = error_message

        return self.patch_staging_record(
            staging_record_id,
            payload,
        )

    def create_staging_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /api/v1/staging-records/ — register a document for extraction.

        Returns the created record dict (contains the public `id`).
        """
        resp = self._client.post(
            f"{self._base_url}/api/v1/staging-records/",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def patch_staging_record(self, staging_record_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """PATCH /api/v1/staging-records/{id} — write back observations + status."""
        resp = self._client.patch(
            f"{self._base_url}/api/v1/staging-records/{staging_record_id}",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FhirStagingClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
