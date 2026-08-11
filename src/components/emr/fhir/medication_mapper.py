"""FHIR MedicationRequest mapper."""

from fhir.resources.medicationrequest import MedicationRequest


class MedicationRequestMapper:
    def map(self, medication: str, patient_id: str) -> MedicationRequest:
        return MedicationRequest(
            status="active",
            intent="order",
            medication={"concept": {"text": medication}},
            subject={"reference": f"Patient/{patient_id}"},
        )
