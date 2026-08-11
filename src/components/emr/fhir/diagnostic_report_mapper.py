"""FHIR DiagnosticReport mapper."""

from fhir.resources.diagnosticreport import DiagnosticReport


class DiagnosticReportMapper:
    def map(self, record: dict, patient_id: str) -> DiagnosticReport:
        return DiagnosticReport(
            status="final",
            code={"text": record.get("source_file", "Medical Report")},
            subject={"reference": f"Patient/{patient_id}"},
            effectiveDateTime=record.get("report_date"),
            conclusion=record.get("summary"),
        )
