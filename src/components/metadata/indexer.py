"""MetadataIndexer — scans wiki directories, builds MetadataEntry objects."""

import hashlib
import logging
import re
from pathlib import Path
from .repository import AbstractMetadataRepository
from .models import MetadataEntry, EntityType

logger = logging.getLogger(__name__)

FLAT_DIR_TO_TYPE: dict[str, EntityType] = {
    "Doctors": EntityType.DOCTOR, "Diseases": EntityType.DISEASE,
    "Procedures": EntityType.PROCEDURE, "Hospitals": EntityType.HOSPITAL,
    "Medications": EntityType.MEDICATION,
}


class MetadataIndexer:
    def __init__(self, repo: AbstractMetadataRepository):
        self._repo = repo

    async def build_from_wiki(self, wiki_dir: Path) -> int:
        wiki_dir = Path(wiki_dir)
        count = 0
        for dir_name, entity_type in FLAT_DIR_TO_TYPE.items():
            dir_path = wiki_dir / dir_name
            if not dir_path.is_dir():
                continue
            for md_file in sorted(dir_path.glob("*.md")):
                entry = self._parse_page(md_file, entity_type, wiki_dir)
                if entry:
                    await self._repo.upsert(entry)
                    count += 1

        patients_dir = wiki_dir / "Patients"
        if patients_dir.is_dir():
            for patient_dir in sorted(patients_dir.iterdir()):
                if not patient_dir.is_dir():
                    continue
                patient_file = patient_dir / "patient.md"
                if patient_file.exists():
                    entry = self._parse_page(patient_file, EntityType.PATIENT, wiki_dir)
                    if entry:
                        await self._repo.upsert(entry)
                        count += 1
                reports_dir = patient_dir / "Reports"
                if reports_dir.is_dir():
                    for report_file in sorted(reports_dir.rglob("*.md")):
                        entry = self._parse_page(report_file, EntityType.REPORT, wiki_dir)
                        if entry:
                            await self._repo.upsert(entry)
                            count += 1

        logger.info(f"Metadata index built — {count} entities from {wiki_dir}")
        return count

    def _parse_page(self, md_file: Path, entity_type: EntityType, wiki_dir: Path) -> MetadataEntry | None:
        content = md_file.read_text(encoding="utf-8")
        title = self._extract_title(content, md_file)
        if not title:
            return None
        return MetadataEntry(
            id=self._make_id(entity_type, title), label=title, entity_type=entity_type,
            slug=md_file.stem, source_file=str(md_file.relative_to(wiki_dir)),
            references=self._extract_references(content),
            metadata=self._extract_metadata(content, entity_type))

    @staticmethod
    def _extract_title(content: str, md_file: Path) -> str | None:
        m = re.match(r"^# (.+)", content)
        return m.group(1).strip() if m else (md_file.stem.replace("-", " ").title() or None)

    @staticmethod
    def _extract_references(content: str) -> list[str]:
        return re.findall(r"\[\[([^]]+)\]\]", content)

    @staticmethod
    def _extract_metadata(content: str, entity_type: EntityType) -> dict:
        meta: dict = {}
        if entity_type == EntityType.PATIENT:
            m = re.search(r"^## Patient ID\s*\n+\s*(\S[^\n]*)", content, re.MULTILINE)
            if m:
                meta["patient_id"] = m.group(1).strip()
        elif entity_type == EntityType.DOCTOR:
            m = re.search(r"^## Hospital\s*\n+\s*\[\[([^\]]+)\]\]", content, re.MULTILINE)
            if m:
                meta["hospital"] = m.group(1).strip()
        elif entity_type == EntityType.REPORT:
            m = re.search(r"^## Report Date\s*\n+\s*(\S[^\n]*)", content, re.MULTILINE)
            if m:
                meta["report_date"] = m.group(1).strip()
            m = re.search(r"^## Patient\s*\n+\s*\[\[([^\]]+)\]\]", content, re.MULTILINE)
            if m:
                meta["patient"] = m.group(1).strip()
        return meta

    @staticmethod
    def _make_id(entity_type: EntityType, label: str) -> str:
        return hashlib.sha256(f"{entity_type.value}:{label.lower().strip()}".encode()).hexdigest()[:16]
