"""Unit tests for the ClinicalDocumentChunker.

Covers: normal Clinical JSON, multiple observations, diagnoses, null/empty
field skipping, missing optional fields, metadata preservation,
deterministic chunk ids, and oversized section splitting.
"""

from __future__ import annotations

import pytest

from src.components.indexing.chunker import ClinicalDocumentChunker


@pytest.fixture
def sample_document() -> dict:
    """A realistic Clinical Domain Model JSON document."""
    return {
        "document_id": "doc-1",
        "report_type": "lab_report",
        "patient_name": "John Doe",
        "patient_id": "10001",
        "summary": "Patient presents with hypertension and anemia.",
        "diagnoses": [
            {"name": "Essential Hypertension", "clinical_status": "active", "severity": "moderate"},
            {"name": "Anemia", "severity": None, "onset_date": None},
        ],
        "observations": [
            {
                "display_name": "Heart Rate",
                "category": "vital_signs",
                "value": 78,
                "unit": "bpm",
                "interpretation": "normal",
                "effective_datetime": "2026-07-05",
            },
            {
                "display_name": "Hemoglobin",
                "category": "laboratory",
                "value": 14.2,
                "unit": "g/dL",
                "reference_range": "13.5-17.5",
                "interpretation": "normal",
                "ai_summary": "Hemoglobin within normal range.",
            },
        ],
        "medications": [
            {"medication_name": "Amlodipine", "dosage": "5 mg", "frequency": "once daily"},
        ],
        "procedures": [],
        "imaging": None,
        "sections": None,
    }


@pytest.fixture
def sample_metadata() -> dict:
    return {
        "patient_id": "10001",
        "file_id": "ABC123",
        "source_file": "report.pdf",
        "report_type": "lab_report",
        "encounter_id": "enc-9",
        "service_request_id": "sr-42",
    }


def test_normal_document_chunks(sample_document, sample_metadata):
    """A normal Clinical JSON produces one chunk per semantic unit."""
    chunks = ClinicalDocumentChunker().chunk(sample_document, sample_metadata)
    types = [c.chunk_type for c in chunks]
    # summary + 2 diagnoses + 2 observations + 1 medication = 6
    assert len(chunks) == 6
    assert types.count("summary") == 1
    assert types.count("diagnosis") == 2
    assert types.count("observation") == 2
    assert types.count("medication") == 1


def test_observation_chunk_content(sample_document, sample_metadata):
    """Observation chunk includes category, value+unit, interpretation, date."""
    chunks = ClinicalDocumentChunker().chunk(sample_document, sample_metadata)
    obs = [c for c in chunks if c.chunk_type == "observation"][0]
    assert "Observation: Heart Rate" in obs.text
    assert "Category: vital_signs" in obs.text
    assert "Value: 78 bpm" in obs.text
    assert "Interpretation: normal" in obs.text
    assert "Effective Date: 2026-07-05" in obs.text


def test_null_and_empty_values_skipped():
    """Null/empty values never appear in chunk text."""
    doc = {
        "summary": "Test doc",
        "diagnoses": [{"name": "Anemia", "severity": None, "onset_date": ""}],
        "observations": [
            {
                "display_name": "BP",
                "category": "vital_signs",
                "value": None,
                "unit": None,
                "reference_range": "",
                "interpretation": None,
            }
        ],
        "medications": [],
        "procedures": [],
        "imaging": None,
        "sections": None,
    }
    chunks = ClinicalDocumentChunker().chunk(doc, {"file_id": "F1", "patient_id": "P1"})
    obs = [c for c in chunks if c.chunk_type == "observation"][0]
    assert "Value:" not in obs.text
    assert "Unit:" not in obs.text
    assert "Reference Range:" not in obs.text
    assert "None" not in obs.text
    # BP observation with no value still has its name
    assert "Observation: BP" in obs.text


def test_missing_optional_fields_ok():
    """A minimal document with only summary produces just a summary chunk."""
    doc = {"summary": "Only a summary.", "observations": [], "diagnoses": [], "medications": [], "procedures": [], "imaging": None, "sections": None}
    chunks = ClinicalDocumentChunker().chunk(doc, {"file_id": "F2", "patient_id": "P2"})
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "summary"


def test_metadata_preserved(sample_document, sample_metadata):
    """Chunk metadata carries the filterable identifiers."""
    chunks = ClinicalDocumentChunker().chunk(sample_document, sample_metadata)
    m = chunks[0].metadata
    assert m.patient_id == "10001"
    assert m.file_id == "ABC123"
    assert m.source_file == "report.pdf"
    assert m.report_type == "lab_report"
    assert m.encounter_id == "enc-9"
    assert m.service_request_id == "sr-42"


def test_filenest_file_id_alias():
    """metadata['filenest_file_id'] maps to file_id when 'file_id' absent."""
    doc = {"summary": "S", "diagnoses": [], "observations": [], "medications": [], "procedures": [], "imaging": None, "sections": None}
    chunks = ClinicalDocumentChunker().chunk(doc, {"filenest_file_id": "FN-77"})
    assert chunks[0].metadata.file_id == "FN-77"


def test_deterministic_chunk_ids(sample_document, sample_metadata):
    """Same input + metadata → identical chunk ids (stable across runs)."""
    c1 = ClinicalDocumentChunker().chunk(sample_document, sample_metadata)
    c2 = ClinicalDocumentChunker().chunk(sample_document, sample_metadata)
    assert [c.chunk_id for c in c1] == [c.chunk_id for c in c2]


def test_chunk_id_changes_with_file_id(sample_document, sample_metadata):
    """Different file_id → different chunk ids (per-patient isolation)."""
    other_meta = dict(sample_metadata, file_id="OTHER")
    c1 = ClinicalDocumentChunker().chunk(sample_document, sample_metadata)
    c2 = ClinicalDocumentChunker().chunk(sample_document, other_meta)
    assert [c.chunk_id for c in c1] != [c.chunk_id for c in c2]


def test_oversized_section_split():
    """A very long section is split by the secondary text splitter."""
    long_text = " ".join(["The quick brown fox jumps over the lazy dog."] * 200)
    doc = {"summary": long_text, "diagnoses": [], "observations": [], "medications": [], "procedures": [], "imaging": None, "sections": None}
    chunker = ClinicalDocumentChunker({"max_chars": 300, "overlap_chars": 30})
    chunks = chunker.chunk(doc, {"file_id": "F3", "patient_id": "P3"})
    # split produces a chunk per sub-chunk; all fit the cap
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.text) <= 300


def test_large_section_uses_configurable_limits():
    """max_chars is honored via config, not hardcoded."""
    long_text = "word " * 500
    doc = {"summary": long_text, "diagnoses": [], "observations": [], "medications": [], "procedures": [], "imaging": None, "sections": None}
    chunker = ClinicalDocumentChunker({"max_chars": 100, "overlap_chars": 10})
    chunks = chunker.chunk(doc, {"file_id": "F4", "patient_id": "P4"})
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c.text) <= 100
