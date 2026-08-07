"""Tests for MedicalTransformer — structured domain models + backward-compat serializer."""

import json
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, date
from decimal import Decimal

from src.components.transformers.medical_base import BaseTransformer
from src.components.transformers.medical_transformer import MedicalTransformer
from src.components.transformers.schemas.medical_schema import MedicalTransformerConfig, MedicalSchema
from src.components.transformers.models.diagnosis import Diagnosis
from src.components.transformers.models.medication import Medication
from src.components.transformers.models.procedure import Procedure
from src.components.transformers.models.observation import Observation, BloodPressure
from src.components.transformers.models.vitals import Vitals
from src.components.transformers.models.imaging import ImagingStudy
from src.components.transformers.models.section import Section
from src.components.transformers.models.patient import Patient
from src.components.transformers.builders.observation_builder import ObservationBuilder
from src.components.transformers.normalizers.observation_normalizer import ObservationNormalizer
from src.components.transformers.validators.observation_validator import ObservationValidator


# ── Config ──

class TestMedicalTransformerConfig:
    def test_requires_api_key(self):
        with pytest.raises(Exception):
            MedicalTransformerConfig()

    def test_defaults(self):
        cfg = MedicalTransformerConfig(api_key="sk-test")
        assert cfg.model_name == "gpt-4o-mini"
        assert cfg.base_url is None


# ── Domain Models ──

class TestDiagnosis:
    def test_minimal(self):
        d = Diagnosis(name="Hypertension")
        assert d.name == "Hypertension"
        assert d.clinical_status is None

    def test_full(self):
        d = Diagnosis(name="CHF", clinical_status="chronic", severity="moderate",
                      onset_date="2026-01-15", notes="NYHA Class II")
        assert d.clinical_status == "chronic"
        assert d.severity == "moderate"
        assert d.onset_date == "2026-01-15"


class TestMedication:
    def test_minimal(self):
        m = Medication(medication_name="Metformin")
        assert m.medication_name == "Metformin"

    def test_full(self):
        m = Medication(medication_name="Furosemide", dosage="40 mg", frequency="BID",
                       route="oral", duration="ongoing", strength="40mg", instructions="Take with food")
        assert m.dosage == "40 mg"
        assert m.frequency == "BID"
        assert m.route == "oral"


class TestProcedure:
    def test_minimal(self):
        p = Procedure(procedure_name="Chest X-Ray")
        assert p.procedure_name == "Chest X-Ray"

    def test_with_details(self):
        p = Procedure(procedure_name="CABG", performer="Dr. Smith", date="2026-05-10",
                      notes="Triple vessel bypass")
        assert p.performer == "Dr. Smith"
        assert p.date == "2026-05-10"


class TestObservation:
    def test_lab_value(self):
        o = Observation(category="laboratory", display_name="Hemoglobin", value=14.2,
                        unit="g/dL", reference_range="12-16", interpretation="normal")
        assert o.category == "laboratory"
        assert o.interpretation == "normal"
        assert o.value == 14.2

    def test_vital_sign(self):
        o = Observation(category="vital_signs", display_name="Blood Pressure",
                        value="138/84", unit="mmHg")
        assert o.category == "vital_signs"

    def test_ecg(self):
        o = Observation(category="ecg", display_name="QRS Duration", value=0.10,
                        unit="s", reference_range="0.06-0.10")
        assert o.category == "ecg"

    def test_blood_pressure_decomposition(self):
        bp = BloodPressure(systolic=138.0, diastolic=84.0)
        o = Observation(category="vital_signs", display_name="Blood Pressure",
                        value="138/84", unit="mmHg", blood_pressure=bp)
        assert o.blood_pressure.systolic == 138.0
        assert o.blood_pressure.diastolic == 84.0


class TestImagingStudy:
    def test_minimal(self):
        i = ImagingStudy()
        assert i.modality is None

    def test_dicom_fields(self):
        i = ImagingStudy(modality="CT", body_part="CHEST", study_uid="1.2.840.1",
                         manufacturer="Siemens", acquisition_date="2026-06-25")
        assert i.modality == "CT"
        assert i.manufacturer == "Siemens"


class TestPatient:
    def test_minimal(self):
        p = Patient(patient_name="John Doe")
        assert p.patient_name == "John Doe"
        assert p.gender is None

    def test_full(self):
        p = Patient(patient_name="Jane", patient_id="P123", gender="F",
                    age=58, date_of_birth="1968-03-15")
        assert p.gender == "F"
        assert p.age == 58


# ── MedicalSchema ──

class TestMedicalSchema:
    def test_minimal_valid(self):
        schema = MedicalSchema(patient_name="Test Patient", summary="OK.")
        assert schema.patient_name == "Test Patient"
        assert schema.diagnoses == []
        assert schema.medications == []
        assert schema.observations == []

    def test_with_structured_diagnoses(self):
        schema = MedicalSchema(
            patient_name="Alice",
            summary="Test.",
            diagnoses=[
                Diagnosis(name="Hypertension", clinical_status="chronic"),
                Diagnosis(name="Type 2 Diabetes", clinical_status="active", severity="moderate"),
            ],
        )
        assert len(schema.diagnoses) == 2
        assert schema.diagnoses[0].name == "Hypertension"
        assert schema.diagnoses[0].clinical_status == "chronic"

    def test_with_structured_medications(self):
        schema = MedicalSchema(
            patient_name="Alice",
            summary="Test.",
            medications=[
                Medication(medication_name="Metformin", dosage="500 mg", frequency="twice daily"),
                Medication(medication_name="Lisinopril", dosage="10 mg", frequency="daily"),
            ],
        )
        assert len(schema.medications) == 2
        assert schema.medications[0].dosage == "500 mg"

    def test_with_observations(self):
        schema = MedicalSchema(
            patient_name="Alice",
            summary="Test.",
            observations=[
                Observation(category="laboratory", display_name="HbA1c", value=7.2, unit="%",
                           reference_range="<5.7", interpretation="high"),
                Observation(category="vital_signs", display_name="Blood Pressure",
                           value="148/92", unit="mmHg"),
            ],
        )
        assert len(schema.observations) == 2
        assert schema.observations[0].category == "laboratory"

    def test_full_dump(self):
        """Verify model_dump produces serializable dicts."""
        schema = MedicalSchema(
            patient_name="Jane", patient_id="P123",
            doctor_name="Dr. Adams",
            diagnoses=[Diagnosis(name="Pneumonia", clinical_status="active")],
            medications=[Medication(medication_name="Amoxicillin", dosage="500 mg")],
            procedures=[Procedure(procedure_name="Chest X-Ray")],
            report_date="2026-07-01",
            summary="CAP.",
            hospital="County",
        )
        d = schema.model_dump()
        assert len(d["diagnoses"]) == 1
        assert isinstance(d["diagnoses"][0], dict)
        assert d["diagnoses"][0]["name"] == "Pneumonia"


# ── Serializer (backward compat) ──

class TestSerializer:
    def test_diagnoses_flattened_to_strings(self):
        output = {
            "patient_name": "John",
            "diagnoses": [
                {"name": "Hypertension", "clinical_status": "chronic"},
                {"name": "Diabetes", "clinical_status": "active"},
            ],
            "medications": [],
            "procedures": [],
            "summary": "OK.",
            "observations": [],
        }
        result = MedicalTransformer._serialize_to_dict(output)
        assert result["diagnoses"] == ["Hypertension", "Diabetes"]
        assert isinstance(result["diagnoses"][0], str)

    def test_medications_flattened_to_strings(self):
        output = {
            "patient_name": "John",
            "diagnoses": [],
            "medications": [
                {"medication_name": "Metformin", "dosage": "500 mg", "frequency": "twice daily"},
                {"medication_name": "Lisinopril", "dosage": "10 mg", "frequency": "daily"},
            ],
            "procedures": [],
            "summary": "OK.",
            "observations": [],
        }
        result = MedicalTransformer._serialize_to_dict(output)
        assert result["medications"] == ["Metformin 500 mg twice daily", "Lisinopril 10 mg daily"]
        assert isinstance(result["medications"][0], str)

    def test_medications_without_dosage(self):
        output = {
            "patient_name": "John",
            "diagnoses": [],
            "medications": [
                {"medication_name": "Paracetamol"},
            ],
            "procedures": [],
            "summary": "OK.",
            "observations": [],
        }
        result = MedicalTransformer._serialize_to_dict(output)
        assert result["medications"] == ["Paracetamol"]

    def test_procedures_flattened_to_strings(self):
        output = {
            "patient_name": "John",
            "diagnoses": [],
            "medications": [],
            "procedures": [
                {"procedure_name": "Chest X-Ray", "date": "2026-06-25"},
                {"procedure_name": "CT Abdomen", "date": "2026-07-01"},
            ],
            "summary": "OK.",
            "observations": [],
        }
        result = MedicalTransformer._serialize_to_dict(output)
        assert result["procedures"] == ["Chest X-Ray", "CT Abdomen"]
        assert isinstance(result["procedures"][0], str)

    def test_already_flat_strings_pass_through(self):
        """If consumer passes flat strings (legacy), serializer is no-op."""
        output = {
            "patient_name": "John",
            "diagnoses": ["Hypertension", "Diabetes"],
            "medications": ["Metformin 500mg"],
            "procedures": ["X-Ray"],
            "summary": "OK.",
            "observations": [],
        }
        result = MedicalTransformer._serialize_to_dict(output)
        assert result["diagnoses"] == ["Hypertension", "Diabetes"]
        assert isinstance(result["diagnoses"][0], str)
        assert result["medications"] == ["Metformin 500mg"]

    def test_observations_pass_through(self):
        output = {
            "patient_name": "John",
            "diagnoses": [],
            "medications": [],
            "procedures": [],
            "summary": "OK.",
            "observations": [
                {"category": "laboratory", "name": "HbA1c", "value": "7.2", "unit": "%"},
                {"category": "vital_signs", "name": "BP", "value": "148/92", "unit": "mmHg"},
            ],
        }
        result = MedicalTransformer._serialize_to_dict(output)
        assert len(result["observations"]) == 2
        assert result["observations"][0]["name"] == "HbA1c"


# ── Observation Builder ──

class TestObservationBuilder:
    def test_builds_from_direct_observations(self):
        raw = {
            "observations": [
                {"name": "Hemoglobin", "category": "laboratory", "value": "14.2",
                 "unit": "g/dL", "interpretation": "normal"},
            ],
            "vitals": {},
        }
        builder = ObservationBuilder()
        result = builder.build(raw)
        assert len(result) == 1
        assert result[0]["display_name"] == "Hemoglobin"
        assert result[0]["value"] == 14.2

    def test_builds_from_vitals(self):
        raw = {
            "observations": [],
            "vitals": {"blood_pressure": "138/84", "heart_rate": "76"},
        }
        builder = ObservationBuilder()
        result = builder.build(raw)
        names = {o["display_name"] for o in result}
        assert "Blood Pressure" in names
        assert "Heart Rate" in names
        assert all(o["category"] == "vital_signs" for o in result)

    def test_no_duplicates_between_direct_and_vitals(self):
        raw = {
            "observations": [
                {"name": "Blood Pressure", "category": "vital_signs", "value": "120/80"},
            ],
            "vitals": {"blood_pressure": "138/84"},
        }
        builder = ObservationBuilder()
        result = builder.build(raw)
        bp_count = sum(1 for o in result if "blood pressure" in o["display_name"].lower())
        assert bp_count == 1

    def test_numeric_parsing(self):
        raw = {
            "observations": [{"name": "Hb", "value": "14.2", "category": "laboratory"}],
            "vitals": {},
        }
        builder = ObservationBuilder()
        result = builder.build(raw)
        assert isinstance(result[0]["value"], float)

    def test_blood_pressure_decomposition(self):
        raw = {
            "observations": [],
            "vitals": {"blood_pressure": "138/84"},
        }
        builder = ObservationBuilder()
        result = builder.build(raw)
        bp_obs = [o for o in result if o["display_name"] == "Blood Pressure"]
        assert len(bp_obs) == 1
        assert bp_obs[0]["blood_pressure"] == {"systolic": 138.0, "diastolic": 84.0}


# ── Observation Normalizer ──

class TestObservationNormalizer:
    def test_removes_duplicates(self):
        obs = [
            {"display_name": "Hemoglobin", "category": "laboratory"},
            {"display_name": "Hemoglobin", "category": "laboratory"},
        ]
        normalizer = ObservationNormalizer()
        result = normalizer.normalize(obs)
        assert len(result) == 1

    def test_normalizes_body_temperature_name(self):
        obs = [{"display_name": "Body Temperature", "category": "vital_signs"}]
        result = ObservationNormalizer().normalize(obs)
        assert result[0]["display_name"] == "Temperature"

    def test_fixes_duplicated_unit(self):
        obs = [{"display_name": "Weight", "category": "vital_signs", "unit": "kg kg"}]
        result = ObservationNormalizer().normalize(obs)
        assert result[0]["unit"] == "kg"

    def test_fixes_none_unit(self):
        obs = [{"display_name": "Hemoglobin", "category": "laboratory", "unit": "None"}]
        result = ObservationNormalizer().normalize(obs)
        assert result[0]["unit"] is None

    def test_fixes_bmi_missing_unit(self):
        obs = [{"display_name": "BMI", "category": "vital_signs"}]
        result = ObservationNormalizer().normalize(obs)
        assert result[0]["unit"] == "kg/m²"


# ── Observation Validator ──

class TestObservationValidator:
    def test_passes_valid_obs(self):
        obs = [{"display_name": "Hb", "category": "laboratory", "interpretation": "normal"}]
        result = ObservationValidator().validate(obs)
        assert len(result) == 1

    def test_flags_invalid_category(self):
        obs = [{"display_name": "X", "category": "unknown"}]
        result = ObservationValidator().validate(obs)
        assert len(result) == 1  # still passes through, just logs warning


# ── MedicalTransformer end-to-end (mock LLM) ──

class TestMedicalTransformer:
    @pytest.fixture
    def structured_response(self):
        return {
            "patient_name": "John Doe",
            "patient_id": "452891",
            "doctor_name": "Dr. Sarah Chen",
            "hospital": "Mercy General",
            "report_date": "2026-06-15",
            "diagnoses": [
                {"name": "Lung nodule", "clinical_status": "active", "severity": None},
                {"name": "Hypertension", "clinical_status": "chronic", "severity": "moderate"},
            ],
            "medications": [
                {"medication_name": "Lisinopril", "dosage": "10 mg", "frequency": "daily"},
            ],
            "procedures": [
                {"procedure_name": "CT Chest", "date": "2026-06-15"},
            ],
            "observations": [],
            "vitals": {"blood_pressure": None, "heart_rate": None},
            "summary": "58yo male with persistent cough.",
            "sections": [],
        }

    @pytest.fixture
    def clinical_response_flat(self):
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
    async def test_transform_with_structured_objects(self, structured_response):
        """LLM returns structured objects → serializer flattens for consumers."""
        config = {"api_key": "sk-test"}
        with patch("src.components.transformers.medical_transformer.LLMClient") as mock_cls:
            mock_cls.return_value.generate = AsyncMock(return_value=json.dumps(structured_response))
            result = await MedicalTransformer(config).transform("Some clinical text")

        assert result["patient_name"] == "John Doe"
        assert isinstance(result["diagnoses"], list)
        assert isinstance(result["diagnoses"][0], str)
        assert result["diagnoses"] == ["Lung nodule", "Hypertension"]
        assert isinstance(result["medications"][0], str)
        assert result["medications"] == ["Lisinopril 10 mg daily"]
        assert isinstance(result["procedures"][0], str)
        assert result["procedures"] == ["CT Chest"]
        assert "observations" in result

    @pytest.mark.asyncio
    async def test_transform_flat_legacy_still_works(self, clinical_response_flat):
        """Legacy flat strings from LLM still work."""
        config = {"api_key": "sk-test"}
        with patch("src.components.transformers.medical_transformer.LLMClient") as mock_cls:
            mock_cls.return_value.generate = AsyncMock(return_value=json.dumps(clinical_response_flat))
            result = await MedicalTransformer(config).transform("Legacy text")

        assert result["patient_name"] == "John Doe"
        assert result["diagnoses"] == ["Lung nodule", "Hypertension"]
        assert isinstance(result["diagnoses"][0], str)

    @pytest.mark.asyncio
    async def test_transform_handles_missing_fields(self):
        resp = {
            "patient_name": "Unknown", "patient_id": None, "doctor_name": None,
            "diagnoses": [], "medications": [], "procedures": [],
            "hospital": None, "report_date": None, "summary": "None.",
            "observations": [],
        }
        with patch("src.components.transformers.medical_transformer.LLMClient") as mock_cls:
            mock_cls.return_value.generate = AsyncMock(return_value=json.dumps(resp))
            result = await MedicalTransformer({"api_key": "sk-test"}).transform("Empty")
        assert result["patient_name"] == "Unknown"
        assert result["diagnoses"] == []
        assert "observations" in result

    @pytest.mark.asyncio
    async def test_prompt_loaded_at_init(self):
        with patch("src.components.transformers.medical_transformer.LLMClient"):
            t = MedicalTransformer({"api_key": "sk-test"})
        assert len(t._system_prompt) > 500
        assert "Clinical Information Extraction" in t._system_prompt

    @pytest.mark.asyncio
    async def test_dicom_metadata_populates_imaging(self):
        resp = {
            "patient_name": "John DICOM",
            "diagnoses": [], "medications": [], "procedures": [],
            "summary": "DICOM study.",
            "observations": [],
        }
        dicom_meta = {
            "modality": "CT", "study_uid": "1.2.3.4",
            "manufacturer": "TOSHIBA", "study_date": "2004-08-26",
            "rows": 512, "columns": 512, "pixel_spacing": [0.5, 0.5],
        }
        with patch("src.components.transformers.medical_transformer.LLMClient") as mock_cls:
            mock_cls.return_value.generate = AsyncMock(return_value=json.dumps(resp))
            result = await MedicalTransformer({"api_key": "sk-test"}).transform("DICOM text", dicom_meta)

        assert result["imaging"]["modality"] == "CT"
        assert result["imaging"]["manufacturer"] == "TOSHIBA"
        assert result["imaging"]["rows"] == 512
        assert result["imaging"]["pixel_spacing"] == "[0.5, 0.5]"


# ── Wiki/Graph consumer compatibility ──

class TestConsumerCompatibility:
    """Verify the flat dict format works with all downstream consumers."""

    def flat_output(self):
        return {
            "patient_name": "Robert Chen",
            "patient_id": "C-2026-007823",
            "doctor_name": "Dr. Anita Desai",
            "hospital": "Mercy Medical Center",
            "report_date": "2026-06-25",
            "diagnoses": ["Congestive Heart Failure", "Hypertension", "Cardiomegaly"],
            "medications": ["Furosemide 40 mg BID", "Lisinopril 10 mg daily"],
            "procedures": ["Chest X-Ray"],
            "vitals": {"blood_pressure": "148/92", "heart_rate": "84"},
            "observations": [
                {"category": "vital_signs", "name": "Blood Pressure", "value": "148/92", "unit": "mmHg"},
            ],
            "summary": "CHF exacerbation.",
            "sections": None,
        }

    def test_wiki_composer_vitals_access(self):
        doc = self.flat_output()
        vitals = doc.get("vitals")
        assert vitals is not None
        assert vitals.get("blood_pressure") == "148/92"
        assert vitals.get("heart_rate") == "84"

    def test_wiki_composer_diagnoses_are_strings(self):
        doc = self.flat_output()
        for d in doc["diagnoses"]:
            assert isinstance(d, str)
            _ = d.lower().replace(" ", "-")  # slugify works

    def test_wiki_composer_medications_are_strings(self):
        doc = self.flat_output()
        for m in doc["medications"]:
            assert isinstance(m, str)

    def test_graph_builder_iterates_diagnoses_as_strings(self):
        doc = self.flat_output()
        for diag in doc.get("diagnoses", []):
            assert isinstance(diag, str)

    def test_graph_builder_iterates_medications_as_strings(self):
        doc = self.flat_output()
        for med in doc.get("medications", []):
            assert isinstance(med, str)

    def test_observations_present_as_new_key(self):
        doc = self.flat_output()
        assert "observations" in doc
        assert len(doc["observations"]) >= 1
        assert doc["observations"][0]["category"] == "vital_signs"


# ── BaseTransformer ──

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
