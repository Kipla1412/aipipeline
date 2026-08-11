"""FHIR Patient mapper — Approved Clinical Record → FHIR R4 Patient."""

from fhir.resources.patient import Patient
from fhir.resources.humanname import HumanName


class PatientMapper:
    def map(self, record) -> Patient:
        patient = Patient(
            id=self._safe_id(record.get("patient_id")),
            active=True,
        )
        if record.get("patient_name"):
            patient.name = [HumanName(use="official", text=record["patient_name"])]
        if record.get("patient_id"):
            patient.identifier = [
                {
                    "system": "urn:oid:2.16.840.1.113883.19.5",
                    "value": record["patient_id"],
                }
            ]
        return patient

    @staticmethod
    def _safe_id(value: str | None) -> str | None:
        if not value: return None
        return value.lower().replace(" ", "-").replace("_", "-")[:64]
