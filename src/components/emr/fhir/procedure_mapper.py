"""FHIR Procedure mapper."""

from fhir.resources.procedure import Procedure


class ProcedureMapper:
    def map(self, procedure: str, patient_id: str) -> Procedure:
        return Procedure(
            status="completed",
            code={"text": procedure},
            subject={"reference": f"Patient/{patient_id}"},
        )
