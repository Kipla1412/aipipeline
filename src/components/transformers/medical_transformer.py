import json
import logging
from pathlib import Path
from typing import Dict, Any

from .medical_base import BaseTransformer
from .schemas.medical_schema import MedicalTransformerConfig, MedicalSchema
from ..utils.llm import LLMClient

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class MedicalTransformer(BaseTransformer):
    def __init__(self, config: Dict[str, Any]):
        validated = MedicalTransformerConfig(**config)
        self.llm = LLMClient(api_key=validated.api_key, model=validated.model_name, base_url=validated.base_url)
        self._system_prompt = (_PROMPTS_DIR / "clinical_extraction.md").read_text(encoding="utf-8")

    async def transform(self, raw_text: str, dicom_metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
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

        return result

    @staticmethod
    def _build_imaging_study(metadata: Dict[str, Any]) -> Dict[str, Any]:
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
