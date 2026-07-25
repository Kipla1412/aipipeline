"""Filesystem operations for the Patient-Centric Medical Knowledge Base.

Shared knowledge:  Doctors/  Diseases/  Hospitals/  Procedures/  Medications/
Patient workspace: Patients/{slug}/
                     patient.md  index.md  timeline.md  log.md
                     Reports/  Images/
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import logging

logger = logging.getLogger(__name__)


class WikiError(Exception):
    """Base exception for wiki layer failures."""


class FileWriteError(WikiError):
    """Raised when a markdown file cannot be written."""


class InvalidDocumentError(WikiError):
    """Raised when input document is missing required fields."""


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")


class WikiFileManager:
    SHARED_DIRS = ("Doctors", "Diseases", "Medications", "Procedures", "Hospitals")
    PATIENT_SUBDIRS = ("Reports", "Images")

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        for d in self.SHARED_DIRS:
            (self.base_dir / d).mkdir(parents=True, exist_ok=True)
        (self.base_dir / "Patients").mkdir(parents=True, exist_ok=True)
        logger.debug(f"Wiki directories ready under {self.base_dir}")

    def ensure_patient_workspace(self, patient_slug: str) -> Path:
        ws = self.base_dir / "Patients" / patient_slug
        ws.mkdir(parents=True, exist_ok=True)
        for d in self.PATIENT_SUBDIRS:
            (ws / d).mkdir(parents=True, exist_ok=True)
        return ws

    def ensure_readme(self) -> Path:
        readme = self.base_dir / "README.md"
        if readme.exists():
            return readme
        logger.info("Creating README.md")
        content = (
            "# Medical Knowledge Base\n\n"
            "## Overview\n\n"
            "Patient-centric knowledge base generated from medical documents.\n\n"
            "## Navigation\n\n"
            "- [[index|Medical Knowledge Base Index]]\n"
            "- [[Patients]]\n"
            "- [[Doctors]]\n"
            "- [[Diseases]]\n"
            "- [[Medications]]\n"
            "- [[Procedures]]\n"
            "- [[Hospitals]]\n"
        )
        readme.write_text(content, encoding="utf-8")
        return readme

    def _count_section(self, directory: str) -> int:
        path = self.base_dir / directory
        if not path.exists():
            return 0
        if directory == "Patients":
            return len([d for d in path.iterdir() if d.is_dir() and (d / "patient.md").exists()])
        return sum(1 for f in path.glob("*.md"))

    def _count_total_reports(self) -> int:
        patients_dir = self.base_dir / "Patients"
        if not patients_dir.exists():
            return 0
        count = 0
        for patient_dir in patients_dir.iterdir():
            if not patient_dir.is_dir():
                continue
            reports_dir = patient_dir / "Reports"
            if reports_dir.exists():
                count += sum(1 for _ in reports_dir.rglob("*.md"))
        return count

    def _list_patients(self) -> list[str]:
        patients_dir = self.base_dir / "Patients"
        if not patients_dir.exists():
            return []
        return sorted(
            d.name for d in patients_dir.iterdir()
            if d.is_dir() and (d / "patient.md").exists()
        )

    def update_index(self, recent_pages: list[tuple[str, str]] | None = None) -> Path:
        index_path = self.base_dir / "index.md"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            "# Medical Knowledge Base Index",
            "",
            "## Overview",
            "",
            f"- Total Patients: {self._count_section('Patients')}",
            f"- Total Doctors: {self._count_section('Doctors')}",
            f"- Total Diseases: {self._count_section('Diseases')}",
            f"- Total Medications: {self._count_section('Medications')}",
            f"- Total Procedures: {self._count_section('Procedures')}",
            f"- Total Reports: {self._count_total_reports()}",
            "",
            "## Patient Directory",
            "",
        ]
        for p in self._list_patients():
            lines.append(f"- [[{p.replace('-', ' ').title()}]]")
        lines.append("")
        lines.append("## Categories")
        lines.append("")
        lines.extend(["- [[Doctors]]", "- [[Diseases]]", "- [[Medications]]", "- [[Procedures]]", "- [[Hospitals]]", ""])
        if recent_pages:
            lines.append("## Recently Added")
            lines.append("")
            for slug, name in recent_pages[-10:]:
                lines.append(f"- [[{name}]]")
            lines.append("")
        lines.append("## Last Updated")
        lines.append("")
        lines.append(now)
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info("Updated index.md")
        return index_path

    def append_log(self, source_file: str, patient: str, generated_pages: list[str],
                   status: str = "SUCCESS", duration_s: float | None = None) -> Path:
        log_path = self.base_dir / "log.md"
        if not log_path.exists():
            log_path.write_text("# Wiki Processing Log\n\n", encoding="utf-8")
        existing = log_path.read_text(encoding="utf-8").strip()
        if self._log_has_entry(existing, source_file, patient):
            logger.info(f"Log entry already exists for {source_file} [{patient}] — skipping")
            return log_path
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = ["", "---", "", f"## {now}", "", "**Source File:**", "", f"  {source_file}",
                 "", "**Patient:**", "", f"  [[{patient}]]", "", "**Generated Pages:**", ""]
        for page in generated_pages:
            lines.append(f"  - [[{page}]]")
        lines.extend(["", "**Status:**", "", f"  {status}"])
        if duration_s is not None:
            lines.extend(["", f"**Duration:** {duration_s:.2f}s"])
        lines.extend(["", "---"])
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        logger.info("Appended global log entry")
        return log_path

    @staticmethod
    def _log_has_entry(existing: str, source_file: str, patient: str) -> bool:
        return f"  {source_file}" in existing and f"  [[{patient}]]" in existing

    def save_patient_log(self, patient_slug: str, source_file: str, generated_pages: list[str],
                         status: str = "SUCCESS", duration_s: float | None = None) -> Path:
        ws = self.base_dir / "Patients" / patient_slug
        ws.mkdir(parents=True, exist_ok=True)
        log_path = ws / "log.md"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = ["# Patient Processing Log", "", f"**Source File:** {source_file}",
                 f"**Processed:** {now}", f"**Status:** {status}"]
        if duration_s is not None:
            lines.append(f"**Duration:** {duration_s:.2f}s")
        lines.extend(["", "## Generated Pages", ""])
        for page in generated_pages:
            lines.append(f"- `{page}`")
        lines.append("")
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return log_path

    def save_patient_file(self, patient_slug: str, filename: str, content: str) -> Path:
        path = self.base_dir / "Patients" / patient_slug / filename
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            logger.debug(f"Saved Patients/{patient_slug}/{filename}")
            return path
        except OSError as exc:
            raise FileWriteError(f"Failed to write {path}: {exc}") from exc

    def save_report_file(self, patient_slug: str, report_type: str, slug: str, content: str) -> Path:
        report_dir = _REPORT_TYPE_DIR.get(report_type, "Other")
        path = self.base_dir / "Patients" / patient_slug / "Reports" / report_dir / f"{slug}.md"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            logger.debug(f"Saved Patients/{patient_slug}/Reports/{report_dir}/{slug}.md")
            return path
        except OSError as exc:
            raise FileWriteError(f"Failed to write {path}: {exc}") from exc

    def read_patient_file(self, patient_slug: str, filename: str) -> str | None:
        path = self.base_dir / "Patients" / patient_slug / filename
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def rebuild_patient_indexes(self, patient_slug: str, document: dict[str, Any]) -> list[Path]:
        from .composer import ReportComposer
        composer = ReportComposer()
        ws = self.base_dir / "Patients" / patient_slug
        reports_dir = ws / "Reports"
        report_type_groups: dict[str, list[str]] = {}
        report_filenames: list[str] = []
        timeline_reports: list[dict[str, str]] = []
        report_date = document.get("report_date", "")
        if reports_dir.is_dir():
            for rtype_dir in sorted(reports_dir.iterdir()):
                if not rtype_dir.is_dir():
                    continue
                rtype = rtype_dir.name
                for md_file in sorted(rtype_dir.glob("*.md")):
                    label = md_file.stem.replace("-", " ").title()
                    report_type_groups.setdefault(rtype, []).append(label)
                    report_filenames.append(label)
                    timeline_reports.append({"date": report_date, "label": label, "slug": md_file.stem})
        paths: list[Path] = []
        paths.append(self.save_patient_file(patient_slug, "index.md",
            composer.compose_patient_index(document, report_filenames, report_type_groups)))
        paths.append(self.save_patient_file(patient_slug, "timeline.md",
            composer.compose_timeline(document.get("patient_name", patient_slug), timeline_reports)))
        return paths

    def _page_path(self, directory: str, slug: str) -> Path:
        return self.base_dir / directory / f"{slug}.md"

    def save_page(self, directory: str, slug: str, content: str) -> Path:
        path = self._page_path(directory, slug)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            logger.debug(f"Saved {directory}/{slug}.md")
            return path
        except OSError as exc:
            raise FileWriteError(f"Failed to write {path}: {exc}") from exc

    def page_exists(self, directory: str, slug: str) -> bool:
        return self._page_path(directory, slug).exists()

    def read_page(self, directory: str, slug: str) -> str | None:
        path = self._page_path(directory, slug)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def copy_images(self, patient_slug: str, report_type: str, images: list[str | dict[str, str]]) -> int:
        import shutil
        report_dir = _REPORT_TYPE_DIR.get(report_type, "Other")
        dest_dir = self.base_dir / "Patients" / patient_slug / "Images" / report_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for img_src in images:
            if isinstance(img_src, dict):
                img_src = img_src.get("path")
            if not img_src:
                continue
            src = Path(img_src)
            if not src.exists():
                logger.warning(f"Image not found: {src}")
                continue
            dest = dest_dir / src.name
            shutil.copy2(src, dest)
            count += 1
        logger.info(f"Copied {count} images to {dest_dir}")
        return count


_REPORT_TYPE_DIR: dict[str, str] = {
    "mri": "MRI", "ct": "CT", "xray": "X-Ray", "ultrasound": "Ultrasound",
    "ecg": "ECG", "blood_report": "Blood", "lab_report": "LabReports",
    "prescription": "Prescription", "discharge_summary": "DischargeSummary",
    "consultation": "Consultation", "operative_report": "OperativeReports",
    "histopathology": "Pathology", "microbiology": "Microbiology", "other": "Other",
}
