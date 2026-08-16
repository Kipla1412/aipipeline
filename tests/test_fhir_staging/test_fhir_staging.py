"""Tests for the fhir-staging bridge — mapper, client, push service.

- Mapper: transformer observation → fhir-staging ObservationInput shape
- Client: POST/PATCH to the staging API (mocked httpx, no server needed)
- PushService: full register + patch flow (mocked)

No external service or credentials required.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from src.components.fhir_staging.mapper import StagingObservationMapper
from src.components.fhir_staging.client import FhirStagingClient
from src.components.fhir_staging.push_service import StagingPushService


# ── Mapper ──

class TestStagingObservationMapper:
    def test_numeric_value_maps_to_quantity(self):
        obs = {"display_name": "Hemoglobin", "value": 14.2, "unit": "g/dL",
               "category": "laboratory"}
        result = StagingObservationMapper().map(obs)
        assert result["code_display"] == "Hemoglobin"
        assert result["value_quantity_value"] == 14.2
        assert result["value_quantity_unit"] == "g/dL"
        assert result["value_quantity_system"] == "http://unitsofmeasure.org"

    def test_string_value_maps_to_value_string(self):
        obs = {"display_name": "Urine Colour", "value": "Pale Yellow", "category": "laboratory"}
        result = StagingObservationMapper().map(obs)
        assert result["value_string"] == "Pale Yellow"
        assert "value_quantity_value" not in result

    def test_comma_separator_numeric(self):
        obs = {"display_name": "WBC", "value": "13,500", "unit": "cells/cu.mm"}
        result = StagingObservationMapper().map(obs)
        assert result["value_quantity_value"] == 13500.0

    def test_category_mapping(self):
        obs = {"display_name": "BP", "value": 120, "unit": "mmHg", "category": "vital_signs"}
        result = StagingObservationMapper().map(obs)
        assert result["category"][0]["coding_code"] == "vital-signs"

    def test_reference_range_parsed(self):
        obs = {"display_name": "Hb", "value": 14.2, "unit": "g/dL", "reference_range": "13.5-17.5"}
        result = StagingObservationMapper().map(obs)
        rr = result["reference_range"][0]
        assert rr["low_value"] == 13.5
        assert rr["high_value"] == 17.5
        assert rr["low_unit"] == "g/dL"

    def test_reference_range_text_only(self):
        obs = {"display_name": "Cholesterol", "value": 215, "unit": "mg/dL", "reference_range": "<200"}
        result = StagingObservationMapper().map(obs)
        assert result["reference_range"][0]["text"] == "<200"
        assert "low_value" not in result["reference_range"][0]

    def test_interpretation_mapping(self):
        obs = {"display_name": "HbA1c", "value": 7.8, "unit": "%", "interpretation": "high"}
        result = StagingObservationMapper().map(obs)
        assert result["interpretation"][0]["coding_code"] == "HIGH"

    def test_effective_datetime(self):
        obs = {"display_name": "Glucose", "value": 132, "unit": "mg/dL",
               "effective_datetime": "2026-07-15T08:30:00Z"}
        result = StagingObservationMapper().map(obs)
        assert result["effective_date_time"] == "2026-07-15T08:30:00Z"

    def test_empty_obs(self):
        result = StagingObservationMapper().map({})
        assert result["status"] == "preliminary"
        assert "value_quantity_value" not in result


# ── Client (mocked httpx) ──

class TestFhirStagingClient:
    @patch("src.components.fhir_staging.client.PipelineConfig")
    def test_create_staging_record(self, mock_config):
        mock_config.return_value.get_fhir_staging_config.return_value = {
            "base_url": "http://test:8002", "timeout": 30.0
        }
        client = FhirStagingClient()
        client._client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 10001, "status": "pending"}
        client._client.post.return_value = mock_resp

        result = client.create_staging_record({"file_id": "f1", "attachment_title": "a.pdf"})
        assert result["id"] == 10001
        client._client.post.assert_called_once_with(
            "http://test:8002/api/v1/staging-records/",
            json={"file_id": "f1", "attachment_title": "a.pdf"},
        )

    @patch("src.components.fhir_staging.client.PipelineConfig")
    def test_patch_staging_record(self, mock_config):
        mock_config.return_value.get_fhir_staging_config.return_value = {
            "base_url": "http://test:8002", "timeout": 30.0
        }
        client = FhirStagingClient()
        client._client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 10001, "status": "completed"}
        client._client.patch.return_value = mock_resp

        result = client.patch_staging_record(10001, {"status": "completed"})
        assert result["status"] == "completed"
        client._client.patch.assert_called_once_with(
            "http://test:8002/api/v1/staging-records/10001",
            json={"status": "completed"},
        )


# ── PushService (mocked client) ──

class TestStagingPushService:
    @patch("src.components.fhir_staging.push_service.FhirStagingClient")
    def test_push_document_creates_and_patches(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.create_staging_record.return_value = {"id": 10001, "status": "pending"}
        mock_client.patch_staging_record.return_value = {"id": 10001, "status": "completed", "observations": [{}]}
        mock_client_cls.return_value = mock_client

        doc = {
            "observations": [
                {"display_name": "Hemoglobin", "value": 14.2, "unit": "g/dL", "category": "laboratory"},
            ]
        }
        push = StagingPushService()
        result = push.push_document(
            file_id="f-123", filename="report.pdf", content_type="application/pdf",
            size_bytes=100, document=doc, patient_id=10001,
        )

        assert result["status"] == "completed"
        # create called with file metadata + context
        create_payload = mock_client.create_staging_record.call_args[0][0]
        assert create_payload["file_id"] == "f-123"
        assert create_payload["patient_id"] == 10001
        # patch called with mapped observation
        patch_payload = mock_client.patch_staging_record.call_args[0][1]
        assert patch_payload["status"] == "completed"
        assert patch_payload["observations"][0]["code_display"] == "Hemoglobin"

    @patch("src.components.fhir_staging.push_service.FhirStagingClient")
    def test_push_document_no_observations(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.create_staging_record.return_value = {"id": 10002, "status": "pending"}
        mock_client.patch_staging_record.return_value = {"id": 10002, "status": "completed", "observations": []}
        mock_client_cls.return_value = mock_client

        push = StagingPushService()
        result = push.push_document(
            file_id="f-2", filename="x.pdf",
            content_type="application/pdf", size_bytes=100,
            document={},
        )
        assert result["status"] == "completed"
        patch_payload = mock_client.patch_staging_record.call_args[0][1]
        assert patch_payload["observations"] == []
