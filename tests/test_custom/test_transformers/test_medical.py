import json
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, date
from decimal import Decimal
from src.components.transformers.medical_base import BaseTransformer
from src.components.transformers.medical_transformer import MedicalTransformer
from src.components.transformers.schemas.medical_schema import MedicalTransformerConfig, MedicalSchema


class TestMedicalTransformerConfig:
    def test_requires_api_key(self):
        with pytest.raises(Exception):
            MedicalTransformerConfig()

    def test_defaults(self):
        cfg = MedicalTransformerConfig(api_key="sk-test")
        assert cfg.model_name == "gpt-4o-mini"
        assert cfg.base_url is None


class TestMedicalTransformer:
    @pytest.fixture
    def clinical_response(self):
        return {
            "patient_name": "John Doe", "patient_id": "452891",
            "doctor_name": "Dr. Sarah Chen",
            "diagnoses": ["Lung nodule", "Hypertension"],
            "medications": ["Lisinopril 10mg daily"],
            "procedures": ["CT Chest"],
            "hospital": "Mercy General",
            "report_date": "2026-06-15",
            "summary": "58yo male with persistent cough.",
        }

    @pytest.mark.asyncio
    async def test_transform_returns_clean_dict(self, clinical_response):
        config = {"api_key": "sk-test"}
        with patch("src.components.transformers.medical_transformer.LLMClient") as mock_cls:
            mock_cls.return_value.generate = AsyncMock(return_value=json.dumps(clinical_response))
            result = await MedicalTransformer(config).transform("Some clinical text")
        assert result["patient_name"] == "John Doe"
        assert len(result["diagnoses"]) == 2

    @pytest.mark.asyncio
    async def test_transform_handles_missing_fields(self):
        resp = {"patient_name": "Unknown", "patient_id": None, "doctor_name": None,
                "diagnoses": [], "medications": [], "procedures": [],
                "hospital": None, "report_date": None, "summary": "None."}
        with patch("src.components.transformers.medical_transformer.LLMClient") as mock_cls:
            mock_cls.return_value.generate = AsyncMock(return_value=json.dumps(resp))
            result = await MedicalTransformer({"api_key": "sk-test"}).transform("Empty")
        assert result["patient_name"] == "Unknown"
        assert result["diagnoses"] == []

    @pytest.mark.asyncio
    async def test_prompt_loaded_at_init(self):
        with patch("src.components.transformers.medical_transformer.LLMClient"):
            t = MedicalTransformer({"api_key": "sk-test"})
        assert len(t._system_prompt) > 500
        assert "Clinical Information Extraction" in t._system_prompt


class TestMedicalSchema:
    def test_minimal_valid(self):
        schema = MedicalSchema(patient_name="Test Patient", summary="OK.")
        assert schema.patient_name == "Test Patient"
        assert schema.diagnoses == []

    def test_full_dump(self):
        schema = MedicalSchema(patient_name="Jane", patient_id="P123",
                               doctor_name="Dr. Adams", diagnoses=["Pneumonia"],
                               medications=["Amoxicillin"], report_date="2026-07-01",
                               summary="CAP.", hospital="County", procedures=["X-Ray"])
        d = schema.model_dump()
        assert len(d["diagnoses"]) == 1
        assert d["report_date"] == "2026-07-01"


class TestBaseTransformer:
    def test_clean_datetime_to_isoformat(self):
        base = BaseTransformer()
        assert base.clean({"dt": datetime(2026, 7, 5, 14, 30)})["dt"] == "2026-07-05T14:30:00"

    def test_clean_decimal_to_float(self):
        base = BaseTransformer()
        r = base.clean({"val": Decimal("0.954")})
        assert r["val"] == 0.954
        assert isinstance(r["val"], float)

    def test_clean_passes_primitives(self):
        base = BaseTransformer()
        data = {"name": "test", "count": 42, "active": True, "items": [1, 2], "meta": {"k": "v"}}
        assert base.clean(data) == data
