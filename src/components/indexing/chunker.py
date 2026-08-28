"""ClinicalDocumentChunker — converts Clinical Domain Model JSON into semantic chunks.

Single responsibility: structure-aware chunking of clinical JSON into
clean, embeddable text chunks with deterministic ids. No embedding, no
indexing, no modification of the original document.

Chunk types produced (only for sections that actually exist):
    summary, diagnosis, observation, medication, procedure, imaging, section

For observations, one meaningful chunk is created per observation with
its category, display name, value + unit, interpretation, etc. Null and
empty values are never included in the text. If a single semantic chunk
exceeds ``max_chars`` it is split with a secondary text splitter using a
configurable overlap.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .schemas.chunk import ChunkingConfig, ChunkMetadata, ClinicalChunk


class ClinicalDocumentChunker:
    """Structure-aware chunker for Clinical Domain Model JSON."""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Purpose:
            Initializes the chunker with configurable limits.

        Args:
            config (dict | None): Optional keys ``max_chars`` and ``overlap_chars``.
                Defaults to ChunkingConfig defaults (1500 / 150).
        """
        validated = ChunkingConfig(**(config or {}))
        self.max_chars = validated.max_chars
        self.overlap_chars = validated.overlap_chars

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def chunk(self, document: dict[str, Any], metadata: dict[str, Any]) -> list[ClinicalChunk]:
        """
        Purpose:
            Converts a Clinical Domain Model JSON dict into semantic chunks.

        Args:
            document (dict): The clinical JSON (MedicalSchema output).
            metadata (dict): Filterable metadata: patient_id, file_id,
                source_file, report_type, encounter_id, service_request_id.

        Returns:
            list[ClinicalChunk]: Deterministically-ordered, structure-aware chunks.
        """
        doc_meta = self._build_metadata(metadata)
        chunks: list[ClinicalChunk] = []

        # Document summary
        summary = document.get("summary")
        if self._is_not_empty(summary):
            chunks.extend(self._make_chunks("summary", "Document Summary", str(summary), doc_meta))

        # Diagnoses
        for i, item in enumerate(self._as_list(document.get("diagnoses"))):
            text = self._diagnosis_text(item)
            if text:
                chunks.extend(self._make_chunks("diagnosis", f"Diagnosis {i}", text, doc_meta))

        # Observations — one chunk per observation
        for i, item in enumerate(self._as_list(document.get("observations"))):
            text = self._observation_text(item)
            if text:
                chunks.extend(self._make_chunks("observation", f"Observation {i}", text, doc_meta))

        # Medications
        for i, item in enumerate(self._as_list(document.get("medications"))):
            text = self._medication_text(item)
            if text:
                chunks.extend(self._make_chunks("medication", f"Medication {i}", text, doc_meta))

        # Procedures
        for i, item in enumerate(self._as_list(document.get("procedures"))):
            text = self._procedure_text(item)
            if text:
                chunks.extend(self._make_chunks("procedure", f"Procedure {i}", text, doc_meta))

        # Imaging study
        imaging = document.get("imaging")
        if isinstance(imaging, dict):
            text = self._imaging_text(imaging)
            if text:
                chunks.extend(self._make_chunks("imaging", "Imaging Study", text, doc_meta))

        # Free-text sections (heading → content dict or list of {heading, content})
        for i, (heading, content) in enumerate(self._sections(document.get("sections"))):
            if self._is_not_empty(content):
                text = f"{heading}: {content}" if heading else str(content)
                chunks.extend(self._make_chunks("section", f"Section {i}", text, doc_meta))

        return chunks

    # ------------------------------------------------------------------
    # Chunk construction
    # ------------------------------------------------------------------
    def _make_chunks(self, chunk_type: str, stable_id: str, text: str, meta: ChunkMetadata) -> list[ClinicalChunk]:
        """
        Purpose:
            Builds ClinicalChunk(s), splitting oversized text via the
            secondary text splitter into deterministic sub-chunks.

        Returns:
            list[ClinicalChunk]: One chunk normally, several when text exceeds max_chars.
        """
        text = " ".join(str(text).split())
        sub = self._split_oversized(text)
        if not sub:
            sub = [text]
        out = []
        for i, piece in enumerate(sub):
            sub_suffix = f"#{i}" if len(sub) > 1 else ""
            chunk_id = self._chunk_id(meta.file_id, chunk_type, f"{stable_id}{sub_suffix}", piece)
            out.append(ClinicalChunk(chunk_id=chunk_id, chunk_type=chunk_type, text=piece, metadata=meta))
        return out

    @staticmethod
    def _build_metadata(metadata: dict[str, Any]) -> ChunkMetadata:
        """Extract the known metadata fields from the raw metadata dict.

        Identifiers (patient_id, file_id, encounter_id, service_request_id)
        are coerced to strings to tolerate numeric upstream values (e.g.
        patient_id=10001 from the staging API).
        """
        return ChunkMetadata(
            patient_id=ClinicalDocumentChunker._to_str(metadata.get("patient_id")),
            file_id=ClinicalDocumentChunker._to_str(
                metadata.get("file_id") or metadata.get("filenest_file_id")
            ),
            source_file=metadata.get("source_file"),
            report_type=metadata.get("report_type"),
            encounter_id=ClinicalDocumentChunker._to_str(metadata.get("encounter_id")),
            service_request_id=ClinicalDocumentChunker._to_str(
                metadata.get("service_request_id")
            ),
        )

    @staticmethod
    def _to_str(value: Any) -> str | None:
        """Coerce an identifier to string, preserving None."""
        if value is None:
            return None
        return str(value)

    def _chunk_id(self, file_id: str | None, chunk_type: str, stable_id: str, text: str) -> str:
        """
        Purpose:
            Computes a deterministic chunk id from stable identity, not content order.

        Returns:
            str: sha256(file_id|chunk_type|stable_id) truncated to 32 hex chars.
        """
        key = f"{file_id or 'unknown'}|{chunk_type}|{stable_id}"
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    # ------------------------------------------------------------------
    # Per-type text renderers (skip null/empty values)
    # ------------------------------------------------------------------
    @staticmethod
    def _diagnosis_text(item: dict[str, Any]) -> str:
        """Render a Diagnosis as clean text, skipping empty values."""
        if not isinstance(item, dict):
            return ""
        name = item.get("name")
        if not name:
            return ""
        parts = [f"Diagnosis: {name}"]
        _append_labeled(parts, "Status", item.get("clinical_status"))
        _append_labeled(parts, "Severity", item.get("severity"))
        _append_labeled(parts, "Onset", item.get("onset_date"))
        _append_labeled(parts, "Notes", item.get("notes"))
        return "\n".join(parts)

    @staticmethod
    def _observation_text(item: dict[str, Any]) -> str:
        """Render one Observation as clean text, one chunk per observation."""
        if not isinstance(item, dict):
            return ""
        name = item.get("display_name") or item.get("name")
        if not name:
            return ""
        parts = [f"Observation: {name}"]
        _append_labeled(parts, "Category", item.get("category"))
        value = item.get("value")
        unit = item.get("unit")
        if value is not None and value != "":
            parts.append(f"Value: {value}{f' {unit}' if unit else ''}")
        _append_labeled(parts, "Reference Range", item.get("reference_range"))
        _append_labeled(parts, "Interpretation", item.get("interpretation"))
        _append_labeled(parts, "Body Site", item.get("body_site"))
        _append_labeled(parts, "Method", item.get("method"))
        _append_labeled(parts, "Effective Date", item.get("effective_datetime"))
        _append_labeled(parts, "AI Summary", item.get("ai_summary"))
        return "\n".join(parts)

    @staticmethod
    def _medication_text(item: dict[str, Any]) -> str:
        """Render a Medication as clean text."""
        if not isinstance(item, dict):
            return ""
        name = item.get("medication_name")
        if not name:
            return ""
        parts = [f"Medication: {name}"]
        _append_labeled(parts, "Dosage", item.get("dosage"))
        _append_labeled(parts, "Frequency", item.get("frequency"))
        _append_labeled(parts, "Duration", item.get("duration"))
        _append_labeled(parts, "Route", item.get("route"))
        _append_labeled(parts, "Strength", item.get("strength"))
        _append_labeled(parts, "Instructions", item.get("instructions"))
        return "\n".join(parts)

    @staticmethod
    def _procedure_text(item: dict[str, Any]) -> str:
        """Render a Procedure as clean text."""
        if not isinstance(item, dict):
            return ""
        name = item.get("procedure_name")
        if not name:
            return ""
        parts = [f"Procedure: {name}"]
        _append_labeled(parts, "Performer", item.get("performer"))
        _append_labeled(parts, "Date", item.get("date"))
        _append_labeled(parts, "Notes", item.get("notes"))
        return "\n".join(parts)

    @staticmethod
    def _imaging_text(study: dict[str, Any]) -> str:
        """Render ImagingStudy metadata as clean text."""
        parts = []
        modality = study.get("modality")
        body_part = study.get("body_part")
        series_desc = study.get("series_description")
        if modality:
            parts.append(f"Imaging: {modality}")
        if body_part:
            parts.append(f"Body Part: {body_part}")
        _append_labeled(parts, "Series Description", series_desc)
        _append_labeled(parts, "Acquisition Date", study.get("acquisition_date"))
        _append_labeled(parts, "Institution", study.get("institution_name"))
        _append_labeled(parts, "Patient Position", study.get("patient_position"))
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _split_oversized(self, text: str) -> list[str]:
        """
        Purpose:
            Secondary text splitter: splits text longer than max_chars on
            sentence boundaries with configurable overlap.

        Returns:
            list[str]: Sub-chunks, or [] when text fits within max_chars.
        """
        if len(text) <= self.max_chars:
            return []
        chunks: list[str] = []
        remaining = text
        while len(remaining) > self.max_chars:
            cut = remaining.rfind(". ", 0, self.max_chars)
            if cut == -1:
                cut = remaining.rfind(" ", 0, self.max_chars)
            if cut == -1 or cut < self.max_chars // 2:
                cut = self.max_chars
            else:
                cut += 1  # include the ". " / " "
            chunks.append(remaining[:cut].strip())
            start = max(0, cut - self.overlap_chars)
            remaining = remaining[start:].strip()
        if remaining:
            chunks.append(remaining)
        return chunks

    @staticmethod
    def _sections(raw: Any) -> list[tuple[str, str]]:
        """
        Purpose:
            Normalizes the ``sections`` field to a list of (heading, content).

        Returns:
            list[tuple[str, str]]: Heading/content pairs.
        """
        if isinstance(raw, dict):
            return [(str(k), str(v)) for k, v in raw.items() if v]
        if isinstance(raw, list):
            out = []
            for s in raw:
                if isinstance(s, dict):
                    heading = s.get("heading", "")
                    content = s.get("content", "")
                    if content:
                        out.append((str(heading), str(content)))
            return out
        return []

    @staticmethod
    def _as_list(value: Any) -> list:
        """Return a list for list-typed fields; [] for None/non-list."""
        if isinstance(value, list):
            return value
        return []

    @staticmethod
    def _is_not_empty(value: Any) -> bool:
        """
        Purpose:
            Reusable null/empty check: rejects None, empty str, empty list, empty dict.

        Returns:
            bool: True when the value carries meaningful content.
        """
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, dict)):
            return len(value) > 0
        return True


def _append_labeled(parts: list[str], label: str, value: Any) -> None:
    """Append 'Label: value' only when value is meaningful (not None/empty)."""
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    if isinstance(value, (list, dict)) and len(value) == 0:
        return
    parts.append(f"{label}: {value}")
