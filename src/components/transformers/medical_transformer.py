"""Medical Transformer — converts extracted text into Clinical Domain Model.

Composes builder, normalizer, and validator layers for clean SOLID architecture.
Serializes back to backward-compatible flat dict for downstream consumers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .medical_base import BaseTransformer
from .schemas.medical_schema import MedicalTransformerConfig, MedicalSchema
from ..utils.llm import LLMClient
from .builders.observation_builder import ObservationBuilder
from .normalizers.observation_normalizer import ObservationNormalizer
from .validators.observation_validator import ObservationValidator

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class MedicalTransformer(BaseTransformer):
    def __init__(self, config: dict[str, Any]):
        """
        Purpose:
            Initializes the MedicalTransformer with LLM client, extraction prompt,
            and the builder/normalizer/validator observation pipeline.

        Args:
            config (dict): Model name, API key, and optional base URL.
        """
        validated = MedicalTransformerConfig(**config)
        self.llm = LLMClient(
            api_key=validated.api_key,
            model=validated.model_name,
            base_url=validated.base_url,
        )
        self._system_prompt = (_PROMPTS_DIR / "clinical_extraction.md").read_text(encoding="utf-8")
        self._obs_builder = ObservationBuilder()
        self._obs_normalizer = ObservationNormalizer()
        self._obs_validator = ObservationValidator()

    async def transform(
        self, raw_text: str, dicom_metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Purpose:
            Converts extracted text into a structured Clinical Domain Model
            (flat dict format for wiki, graph, and metadata consumers).

        Args:
            raw_text: Extracted document text.
            dicom_metadata: Optional DICOM metadata for imaging documents.

        Returns:
            dict: Flattened clinical record with diagnoses, medications,
                  procedures, observations, vitals, and sections.
        """
        response = await self.llm.generate(
            system_prompt=self._system_prompt,
            user_query=raw_text,
            response_format=MedicalSchema,
        )
        parsed = json.loads(response)
        result = self.clean(parsed)
        self._normalize_sections(result)

        if dicom_metadata:
            result.setdefault("source_type", "dicom")
            result["imaging"] = self._build_imaging_study(dicom_metadata)

        # Build → Normalize → Validate observations
        observations = self._obs_builder.build(result)
        observations = self._obs_normalizer.normalize(observations)
        observations = self._obs_validator.validate(observations)
        result["observations"] = observations

        result = self._serialize_to_dict(result)
        return result

    @staticmethod
    def _serialize_to_dict(data: dict) -> dict:
        """Convert structured domain models back to flat dict for consumers."""
        result = dict(data)

        diagnoses = data.get("diagnoses", [])
        if diagnoses and isinstance(diagnoses[0], dict):
            result["diagnoses"] = [d.get("name", "") for d in diagnoses]

        medications = data.get("medications", [])
        if medications and isinstance(medications[0], dict):
            flat_meds = []
            for m in medications:
                parts = [m.get("medication_name", "")]
                if m.get("dosage"):
                    parts.append(m["dosage"])
                if m.get("frequency"):
                    parts.append(m["frequency"])
                flat_meds.append(" ".join(parts))
            result["medications"] = flat_meds

        procedures = data.get("procedures", [])
        if procedures and isinstance(procedures[0], dict):
            result["procedures"] = [p.get("procedure_name", "") for p in procedures]

        return result

    @staticmethod
    def _build_imaging_study(metadata: dict[str, Any]) -> dict[str, Any]:
        """Build imaging study dict from DICOM metadata."""
        def _float(v):
            if v is None:
                return None
            try:
                return float(str(v))
            except (ValueError, TypeError):
                return None

        def _int(v):
            if v is None:
                return None
            try:
                return int(float(str(v)))
            except (ValueError, TypeError):
                return None

        ps = metadata.get("pixel_spacing")
        if isinstance(ps, (list, tuple)) and len(ps) >= 2:
            pixel_spacing = f"[{ps[0]}, {ps[1]}]"
        else:
            pixel_spacing = str(ps) if ps else None

        return {
            "modality": metadata.get("modality"),
            "body_part": None,
            "study_uid": metadata.get("study_uid"),
            "series_uid": metadata.get("series_uid"),
            "sop_instance_uid": metadata.get("sop_instance_uid"),
            "series_description": metadata.get("series_description"),
            "slice_thickness": _float(metadata.get("slice_thickness")),
            "pixel_spacing": pixel_spacing,
            "rows": _int(metadata.get("rows")),
            "columns": _int(metadata.get("columns")),
            "manufacturer": metadata.get("manufacturer"),
            "model_name": metadata.get("model_name"),
            "acquisition_date": metadata.get("study_date"),
            "window_center": _float(metadata.get("window_center")),
            "window_width": _float(metadata.get("window_width")),
            "patient_position": metadata.get("patient_position"),
            "institution_name": metadata.get("institution_name"),
        }

    @staticmethod
    def _normalize_sections(data: dict) -> None:
        """Convert list-of-sections to heading→content dict."""
        raw = data.get("sections")
        if not raw or not isinstance(raw, list):
            return
        normalized = {}
        for item in raw:
            if isinstance(item, dict):
                heading = item.get("heading", "")
                content = item.get("content", "")
                if heading:
                    normalized[heading] = content
        data["sections"] = normalized if normalized else None
