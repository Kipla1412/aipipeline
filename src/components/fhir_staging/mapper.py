"""Map Clinical Domain Model observations → fhir-staging ObservationInput shape.

Bridges the aiplatform transformer's flat observation dicts to the
fhir-staging API contract (app/schemas/staging_record/input/observation.py):

    aiplatform:  {"display_name", "value", "unit", "reference_range", "interpretation", "category"}
    fhir-staging: {"code_display", "value_quantity_value", "value_quantity_unit",
                   "category": [{coding_system, coding_code, coding_display}],
                   "reference_range": [{low_value, high_value, text}], ...}

The mapping is intentionally thin: display_name → code_display, category →
coding_code, value → value_quantity_*, reference_range text → text. Terminology
mapping (LOINC codes) happens later in a dedicated layer.
"""

from __future__ import annotations

import re
from typing import Any

_OBSERVATION_CATEGORY_CODES = {
    "vital_signs": "vital-signs",
    "laboratory": "laboratory",
    "imaging": "imaging",
    "ecg": "procedure",
    "pathology": "laboratory",
    "microbiology": "laboratory",
}


class StagingObservationMapper:
    """Single responsibility: transformer observation → fhir-staging input dict."""

    def map(self, obs: dict[str, Any]) -> dict[str, Any]:
        name = obs.get("display_name") or obs.get("name") or ""
        value = obs.get("value")
        unit = obs.get("unit")
        category = obs.get("category", "")

        result: dict[str, Any] = {
            "status": "preliminary",  # freshly extracted — unverified
            "code_display": name,
            "code_text": name,
        }

        # Category → FHIR observation-category coding
        cat_code = _OBSERVATION_CATEGORY_CODES.get(category)
        if cat_code:
            result["category"] = [
                {
                    "coding_system": "http://terminology.hl7.org/CodeSystem/observation-category",
                    "coding_code": cat_code,
                    "coding_display": category.replace("_", " ").title(),
                }
            ]

        # Value → valueQuantity when numeric, valueString otherwise
        if value is not None:
            if isinstance(value, (int, float)) or (
                isinstance(value, str) and self._is_numeric(value)
            ):
                result["value_quantity_value"] = self._to_float(value)
                result["value_quantity_unit"] = unit
                result["value_quantity_code"] = unit
                result["value_quantity_system"] = "http://unitsofmeasure.org"
            else:
                result["value_string"] = str(value)

        # Reference range → referenceRange[0].text (structured low/high when parseable)
        ref_range = obs.get("reference_range")
        if ref_range:
            result["reference_range"] = [self._map_reference_range(ref_range, unit)]

        # Interpretation → interpretation[] coding
        interpretation = obs.get("interpretation")
        if interpretation:
            result["interpretation"] = [
                {
                    "coding_system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                    "coding_code": str(interpretation).upper(),
                    "coding_display": str(interpretation),
                }
            ]

        # Effective datetime
        effective = obs.get("effective_datetime")
        if effective:
            result["effective_date_time"] = effective

        # AI summary → summary (colleague added `summary` to the staging API schema)
        ai_summary = obs.get("ai_summary")
        if ai_summary:
            result["summary"] = str(ai_summary)

        return result

    @staticmethod
    def _map_reference_range(ref_range: Any, unit: str | None) -> dict[str, Any]:
        """Best-effort: '13.5-17.5' → low/high; '>40' → text only."""
        text = str(ref_range).strip()
        m = re.match(r"^<?\s*([\d.]+)\s*[-–]\s*([\d.]+)$", text)
        if m:
            return {
                "low_value": float(m.group(1)),
                "low_unit": unit,
                "high_value": float(m.group(2)),
                "high_unit": unit,
                "text": text,
            }
        return {"text": text}

    @staticmethod
    def _is_numeric(s: str) -> bool:
        try:
            float(s.replace(",", ""))
            return True
        except ValueError:
            return False

    @staticmethod
    def _to_float(value: Any) -> float:
        """Convert to float, tolerating comma thousand-separators ('13,500' → 13500.0)."""
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).replace(",", "").strip())
