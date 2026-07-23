"""Base plugin contract + PluginRegistry for medical report wiki rendering.

Every report type plugin must implement BaseMedicalReportPlugin.
WikiGenerator depends ONLY on this abstraction.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable
import logging

from .file_manager import WikiFileManager, slugify, InvalidDocumentError
from .composer import ReportComposer
from . import templates

logger = logging.getLogger(__name__)

REPORT_TYPE_DIRECTORY: dict[str, str] = {
    "mri": "MRI", "ct": "CT", "xray": "X-Ray", "ultrasound": "Ultrasound",
    "ecg": "ECG", "blood_report": "Blood", "lab_report": "LabReports",
    "prescription": "Prescription", "discharge_summary": "DischargeSummary",
    "consultation": "Consultation", "operative_report": "OperativeReports",
    "histopathology": "Pathology", "microbiology": "Microbiology", "other": "Other",
}


class BaseMedicalReportPlugin(ABC):
    def __init__(self):
        self.composer = ReportComposer()

    @property
    @abstractmethod
    def report_type(self) -> str: ...

    @property
    @abstractmethod
    def report_label(self) -> str: ...

    @property
    @abstractmethod
    def section_order(self) -> list[str]: ...

    def validate(self, document: dict[str, Any]) -> None:
        if not document.get("patient_name"):
            raise InvalidDocumentError(f"{self.report_label}: missing patient_name")

    def render(self, document: dict[str, Any], fm: WikiFileManager, source_filename: str) -> list[Path]:
        self.validate(document)
        paths: list[Path] = []

        patient = document.get("patient_name", "Unknown")
        patient_slug = slugify(patient)
        doctor = document.get("doctor_name")
        hospital = document.get("hospital")
        report_type = document.get("report_type", "")
        report_date = document.get("report_date", "")
        report_id = source_filename.rsplit(".", 1)[0] if source_filename else patient
        report_slug = slugify(report_id)

        fm.ensure_patient_workspace(patient_slug)
        paths.append(fm.save_patient_file(patient_slug, "patient.md",
            self.render_patient_page(document, None, source_filename)))
        paths.append(fm.save_report_file(patient_slug, report_type, report_slug,
            self.render_report_page(document, source_filename, patient_slug)))
        paths.extend(fm.rebuild_patient_indexes(patient_slug, document))

        for diag in document.get("diagnoses", []):
            content = templates.disease_page(diag, [patient], document.get("procedures", []))
            existing = fm.read_page("Diseases", slugify(diag))
            if existing:
                content = _merge_section(existing, content, "## Patients")
            paths.append(fm.save_page("Diseases", slugify(diag), content))

        meds = document.get("medications", [])
        if meds:
            paths.append(fm.save_page("Medications", slugify(patient),
                templates.medication_page(patient, meds)))

        for proc in document.get("procedures", []):
            content = templates.procedure_page(proc, [patient], document.get("summary", ""))
            existing = fm.read_page("Procedures", slugify(proc))
            if existing:
                content = _merge_section(existing, content, "## Related Patients")
            paths.append(fm.save_page("Procedures", slugify(proc), content))

        if doctor:
            content = templates.doctor_page(doctor, hospital, [patient])
            existing = fm.read_page("Doctors", slugify(doctor))
            if existing:
                content = _merge_section(existing, content, "## Patients")
            paths.append(fm.save_page("Doctors", slugify(doctor), content))

        if hospital:
            content = templates.hospital_page(hospital, [doctor] if doctor else [], [patient])
            existing = fm.read_page("Hospitals", slugify(hospital))
            if existing:
                content = _merge_section(existing, content, "## Patients")
            paths.append(fm.save_page("Hospitals", slugify(hospital), content))

        fm.save_patient_log(patient_slug, source_file=source_filename,
            generated_pages=[p.relative_to(fm.base_dir).as_posix() for p in paths])

        images = document.get("images", [])
        if images:
            fm.copy_images(patient_slug, report_type, images)

        return paths

    def render_patient_page(self, document: dict[str, Any], ordered_sections: dict[str, str] | None, source_filename: str = "") -> str:
        return self.composer.compose_patient_page(document, source_filename=source_filename)

    def render_report_page(self, document: dict[str, Any], source_filename: str, patient_slug: str = "") -> str:
        return self.composer.compose_report_page(document, source_filename, patient_slug)


class PluginRegistry:
    _plugins: dict[str, BaseMedicalReportPlugin] = {}

    @classmethod
    def register(cls, plugin: BaseMedicalReportPlugin) -> None:
        cls._plugins[plugin.report_type] = plugin
        logger.info(f"Registered plugin: {plugin.report_type} ({plugin.report_label})")

    @classmethod
    def get(cls, report_type: str | None) -> BaseMedicalReportPlugin:
        if report_type and report_type.lower() in cls._plugins:
            return cls._plugins[report_type.lower()]
        return cls._plugins["other"]

    @classmethod
    def reports_directory(cls, report_type: str | None) -> str:
        if report_type:
            return REPORT_TYPE_DIRECTORY.get(report_type.lower(), "Other")
        return "Other"

    @classmethod
    def list_types(cls) -> Iterable[str]:
        return cls._plugins.keys()


def _load_plugins() -> None:
    if _load_plugins._loaded:
        return
    from . import plugins as _p
    import importlib, pkgutil
    for _, name, _ in pkgutil.iter_modules(_p.__path__, _p.__name__ + "."):
        importlib.import_module(name)
    _load_plugins._loaded = True

_load_plugins._loaded = False


def _merge_section(existing: str, new: str, heading: str) -> str:
    pattern = rf"^{re.escape(heading)}\n\n(.*?)(?=\n##|\Z)"
    me = re.search(pattern, existing, re.DOTALL | re.MULTILINE)
    mn = re.search(pattern, new, re.DOTALL | re.MULTILINE)
    if not me or not mn:
        return new
    existing_items = re.findall(r"^- \[\[(.+)\]\]", me.group(1), re.MULTILINE)
    new_items = re.findall(r"^- \[\[(.+)\]\]", mn.group(1), re.MULTILINE)
    added = [i for i in new_items if i not in existing_items]
    if not added:
        return existing
    suffix = "\n".join(f"- [[{i}]]" for i in added)
    return existing[: me.end(1)] + "\n" + suffix + "\n" + existing[me.end(1):]
