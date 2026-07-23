"""ReportComposer — assembles markdown for patient workspace files.

Patient workspace: patient.md, index.md, timeline.md
Report pages: patient/Reports/{type}/{report}.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .file_manager import slugify

_REPORT_TYPE_DIR: dict[str, str] = {
    "mri": "MRI", "ct": "CT", "xray": "X-Ray", "ultrasound": "Ultrasound",
    "ecg": "ECG", "blood_report": "Blood", "lab_report": "LabReports",
    "prescription": "Prescription", "discharge_summary": "DischargeSummary",
    "consultation": "Consultation", "operative_report": "OperativeReports",
    "histopathology": "Pathology", "microbiology": "Microbiology", "other": "Other",
}


class ReportComposer:
    """Pure markdown composition for patient-centric Wiki."""

    def compose_patient_page(self, document: dict[str, Any], report_filenames: list[str] = (), source_filename: str = "") -> str:
        patient = document.get("patient_name", "Unknown")
        patient_id = document.get("patient_id")
        doctor = document.get("doctor_name")
        hospital = document.get("hospital")
        diagnoses = document.get("diagnoses", [])
        medications = document.get("medications", [])
        procedures = document.get("procedures", [])
        vitals = document.get("vitals")
        summary = document.get("summary", "")

        lines = [f"# {patient}", ""]

        lines.append("## Patient Information")
        lines.append("")
        if patient_id:
            lines.append(f"- **Patient ID:** {patient_id}")
        lines.append("")

        if vitals:
            lines.append("## Vital Signs")
            lines.append("")
            if vitals.get("blood_pressure"):
                lines.append(f"- **BP:** {vitals['blood_pressure']}")
            if vitals.get("heart_rate"):
                lines.append(f"- **HR:** {vitals['heart_rate']}")
            if vitals.get("temperature"):
                lines.append(f"- **Temp:** {vitals['temperature']}")
            if vitals.get("weight"):
                lines.append(f"- **Weight:** {vitals['weight']}")
            if vitals.get("height"):
                lines.append(f"- **Height:** {vitals['height']}")
            if vitals.get("bmi"):
                lines.append(f"- **BMI:** {vitals['bmi']}")
            lines.append("")

        lines.append("## Care Team")
        lines.append("")
        if doctor:
            lines.append(f"- **Doctor:** [[{doctor}]]")
        if hospital:
            lines.append(f"- **Hospital:** [[{hospital}]]")
        if not doctor and not hospital:
            lines.append("No care team recorded.")
        lines.append("")

        if diagnoses:
            lines.append("## Diagnoses")
            lines.append("")
            for d in diagnoses:
                lines.append(f"- [[{d}]]")
            lines.append("")

        if medications:
            lines.append("## Current Medications")
            lines.append("")
            for m in medications:
                lines.append(f"- {m}")
            lines.append("")

        if procedures:
            lines.append("## Procedures")
            lines.append("")
            for p in procedures:
                lines.append(f"- [[{p}]]")
            lines.append("")

        lines.append("## Latest Clinical Summary")
        lines.append("")
        lines.append(summary or "No summary available.")
        lines.append("")

        lines.append("## Navigation")
        lines.append("")
        lines.append("- [[index|Patient Index]]")
        lines.append("- [[timeline|Medical Timeline]]")
        if report_filenames:
            lines.append("")
            lines.append("### Reports")
            lines.append("")
            for rf in report_filenames:
                lines.append(f"- [[{rf}]]")

        return "\n".join(lines) + "\n"

    def compose_patient_index(
        self,
        document: dict[str, Any],
        report_filenames: list[str],
        report_type_groups: dict[str, list[str]],
        image_count: int = 0,
    ) -> str:
        patient = document.get("patient_name", "Unknown")
        diagnoses = document.get("diagnoses", [])
        procedures = document.get("procedures", [])
        doctor = document.get("doctor_name")
        hospital = document.get("hospital")

        lines = [
            f"# {patient}",
            "",
            "## Patient Overview",
            "",
            "[[patient|Patient Profile]]",
            "",
            "## Timeline",
            "",
            "[[timeline|Medical Timeline]]",
            "",
            "## Reports",
            "",
        ]

        for rtype, reports in report_type_groups.items():
            lines.append(f"### {rtype}")
            lines.append("")
            for r in reports:
                lines.append(f"- [[{r}]]")
            lines.append("")

        if image_count > 0:
            lines.append("## Images")
            lines.append("")
            lines.append(f"_See Images/ directory — {image_count} image(s)_")
            lines.append("")

        lines.append("## Related Knowledge")
        lines.append("")
        if doctor:
            lines.append(f"- [[{doctor}]]")
        if hospital:
            lines.append(f"- [[{hospital}]]")
        for d in diagnoses:
            lines.append(f"- [[{d}]]")
        for p in procedures:
            lines.append(f"- [[{p}]]")
        lines.append("")

        return "\n".join(lines) + "\n"

    def compose_timeline(
        self,
        patient: str,
        reports: list[dict[str, str]],
    ) -> str:
        reports.sort(key=lambda r: r.get("date", ""))

        lines = [f"# {patient} — Medical Timeline", ""]

        if not reports:
            lines.append("No reports recorded.")
            return "\n".join(lines) + "\n"

        current_year: str | None = None
        for r in reports:
            date = r.get("date", "Unknown")
            year = date[:4] if date != "Unknown" and len(date) >= 4 else "Unknown"
            if year != current_year:
                current_year = year
                lines.append("")
                lines.append(f"## {current_year}")
                lines.append("")

            lines.append(f"- **{date}** — [[{r['slug']}|{r['label']}]]")

        lines.append("")
        return "\n".join(lines) + "\n"

    def compose_report_page(self, document: dict[str, Any], source_filename: str, patient_slug: str) -> str:
        patient = document.get("patient_name", "Unknown")
        report_type = document.get("report_type", "")
        images = document.get("images", [])
        report_dir = _REPORT_TYPE_DIR.get(report_type, "Other")

        lines = [
            f"# {source_filename}",
            "",
            f"## Report Type",
            "",
            f"{report_type or 'Unclassified'}",
            "",
            f"## Patient",
            "",
            f"[[../patient|{patient}]]",
            "",
            f"## Doctor",
            "",
            f"{_link_or_na(document.get('doctor_name'))}",
            "",
            f"## Hospital",
            "",
            f"{_link_or_na(document.get('hospital'))}",
            "",
            f"## Report Date",
            "",
            f"{document.get('report_date') or 'N/A'}",
            "",
            f"## Document ID",
            "",
            f"`{document.get('document_id', 'N/A')}`",
            "",
        ]

        if images:
            lines.append("## Images")
            lines.append("")
            for img in images:
                img_name = Path(img).name
                lines.append(f"![{img_name}](../Images/{report_dir}/{img_name})")
            lines.append("")

        lines.append("## Summary")
        lines.append("")
        lines.append(document.get("summary", "No summary available."))

        return "\n".join(lines) + "\n"


def _link_or_na(value: str | None) -> str:
    return f"[[{value}]]" if value else "N/A"
