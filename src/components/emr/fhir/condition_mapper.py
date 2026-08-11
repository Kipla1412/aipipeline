"""FHIR Condition mapper (Diagnosis → Condition)."""

from fhir.resources.condition import Condition
from fhir.resources.codeableconcept import CodeableConcept


class ConditionMapper:
    def map(self, diagnosis: str, patient_id: str) -> Condition:
        return Condition(
            clinicalStatus=CodeableConcept(
                coding=[{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]
            ),
            code=CodeableConcept(text=diagnosis),
            subject={"reference": f"Patient/{patient_id}"},
        )
