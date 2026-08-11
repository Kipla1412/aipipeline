"""FHIR Bundle builder — assembles all typed resources into an R4 Bundle."""

import uuid
from datetime import datetime, timezone

from fhir.resources.bundle import Bundle, BundleEntry, BundleEntryRequest
from fhir.resources.resource import Resource

from .patient_mapper import PatientMapper
from .observation_mapper import ObservationMapper
from .condition_mapper import ConditionMapper
from .medication_mapper import MedicationRequestMapper
from .procedure_mapper import ProcedureMapper
from .diagnostic_report_mapper import DiagnosticReportMapper
from .imaging_mapper import ImagingStudyMapper


class BundleBuilder:
    def __init__(self):
        self._patient_mapper = PatientMapper()
        self._obs_mapper = ObservationMapper()
        self._condition_mapper = ConditionMapper()
        self._med_mapper = MedicationRequestMapper()
        self._proc_mapper = ProcedureMapper()
        self._report_mapper = DiagnosticReportMapper()
        self._imaging_mapper = ImagingStudyMapper()

    def build(self, record: dict) -> Bundle:
        patient_id = self._safe_id(record.get("patient_id") or record.get("patient_name", "unknown"))
        entries: list[BundleEntry] = []

        # Patient
        patient = self._patient_mapper.map(record)
        entries.append(self._entry(patient))

        # Observations
        for obs in record.get("observations", []):
            entries.append(self._entry(self._obs_mapper.map(obs, patient_id)))

        # Conditions
        for dx in record.get("diagnoses", []):
            entries.append(self._entry(self._condition_mapper.map(dx, patient_id)))

        # Medications
        for med in record.get("medications", []):
            entries.append(self._entry(self._med_mapper.map(med, patient_id)))

        # Procedures
        for proc in record.get("procedures", []):
            entries.append(self._entry(self._proc_mapper.map(proc, patient_id)))

        # DiagnosticReport
        entries.append(self._entry(self._report_mapper.map(record, patient_id)))

        # Imaging
        imaging = record.get("imaging")
        if imaging:
            entries.append(self._entry(self._imaging_mapper.map(imaging, patient_id)))

        return Bundle(
            type="document",
            timestamp=datetime.now(timezone.utc),
            entry=entries,
        )

    @staticmethod
    def _entry(resource: Resource) -> BundleEntry:
        return BundleEntry(
            fullUrl=f"urn:uuid:{uuid.uuid4().hex}",
            resource=resource,
        )

    @staticmethod
    def _safe_id(value: str) -> str:
        return value.lower().replace(" ", "-").replace("_", "-")[:64]
