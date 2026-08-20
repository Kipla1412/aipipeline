"""ObservationBuilder — constructs Observation objects from LLM output and vitals.

Single responsibility: build observations. No normalization, no validation.
"""

from __future__ import annotations

import hashlib
from typing import Any

from ..interfaces import IObservationBuilder
from ..models.observation import BloodPressure


_VITAL_MAP: list[tuple[str, str, str]] = [
    ("blood_pressure", "Blood Pressure", "mmHg"),
    ("heart_rate", "Heart Rate", "bpm"),
    ("temperature", "Temperature", "°F"),
    ("weight", "Weight", "kg"),
    ("height", "Height", "cm"),
    ("bmi", "BMI", "kg/m²"),
    ("respiratory_rate", "Respiratory Rate", "/min"),
    ("oxygen_saturation", "Oxygen Saturation", "%"),
]


class ObservationBuilder(IObservationBuilder):
    def build(self, raw_data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Purpose:
            Builds a unified observation list from LLM output and vitals dict.

        Args:
            raw_data (dict): Contains 'observations' (list) and 'vitals' (dict).

        Returns:
            list[dict]: Normalized observation dicts with numeric values and BP decomposition.
        """
        observations: list[dict[str, Any]] = []
        seen: set[str] = set()

        direct = raw_data.get("observations", [])
        if direct and isinstance(direct, list):
            for o in direct:
                if isinstance(o, dict):
                    obs = self._build_one(o)
                    key = obs["display_name"].strip().lower()
                    if key not in seen:
                        seen.add(key)
                        observations.append(obs)

        vitals = raw_data.get("vitals")
        if vitals and isinstance(vitals, dict):
            for key, display_name, unit in _VITAL_MAP:
                value = vitals.get(key)
                if value and display_name.strip().lower() not in seen:
                    seen.add(display_name.strip().lower())
                    obs = self._from_vital(display_name, str(value), unit)
                    observations.append(obs)

        return observations

    def _build_one(self, raw: dict[str, Any]) -> dict[str, Any]:
        """
        Purpose:
            Builds a single observation dict from raw LLM output.

        Returns:
            dict: Observation with id, category, display_name, numeric value, unit, BP.
        """
        name = raw.get("name") or raw.get("display_name") or ""
        value = raw.get("value")
        numeric_value = self._parse_numeric(value)

        obs: dict[str, Any] = {
            "observation_id": raw.get(
                "observation_id",
                hashlib.sha256(f"obs:{name}:{value}".encode()).hexdigest()[:16],
            ),
            "category": raw.get("category", "laboratory"),
            "code": raw.get("code"),
            "display_name": name,
            "value": numeric_value if numeric_value is not None else value,
            "value_type": raw.get("value_type"),
            "unit": raw.get("unit"),
            "reference_range": raw.get("reference_range"),
            "interpretation": raw.get("interpretation"),
            "ai_summary": raw.get("ai_summary") or raw.get("summary"),
            "body_site": raw.get("body_site"),
            "method": raw.get("method"),
            "effective_datetime": raw.get("effective_datetime"),
            "blood_pressure": None,
        }

        if name and "blood pressure" in name.lower() or "bp" == name.lower().strip():
            obs["blood_pressure"] = self._parse_blood_pressure(value)

        return obs

    def _from_vital(self, display_name: str, value: str, unit: str) -> dict[str, Any]:
        """
        Purpose:
            Builds an observation dict from a vitals entry.

        Returns:
            dict: Observation with vital_signs category and parsed numeric value.
        """
        clean_value = value.replace(unit, "").strip() if unit else value
        return {
            "observation_id": hashlib.sha256(f"vital:{display_name}:{value}".encode()).hexdigest()[:16],
            "category": "vital_signs",
            "code": None,
            "display_name": display_name,
            "value": self._parse_numeric(clean_value),
            "value_type": None,
            "unit": unit,
            "reference_range": None,
            "interpretation": None,
            "ai_summary": None,
            "body_site": None,
            "method": None,
            "effective_datetime": None,
            "blood_pressure": self._parse_blood_pressure(clean_value)
            if "blood pressure" in display_name.lower() else None,
        }

    @staticmethod
    def _parse_numeric(value: Any) -> int | float | str | None:
        """
        Purpose:
            Parses a value into int, float, or keeps string.

        Returns:
            int | float | str | None: Best-effort numeric parse.
        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return value
        s = str(value).strip()
        if "/" in s and not s.replace("/", "").replace(".", "").isdigit():
            return s
        try:
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                return s

    @staticmethod
    def _parse_blood_pressure(value: Any) -> dict[str, Any] | None:
        """
        Purpose:
            Decomposes '138/84' into systolic/diastolic dict.

        Returns:
            dict | None: {'systolic': float, 'diastolic': float} or None if unparsable.
        """
        if value is None:
            return None
        s = str(value).strip()
        parts = s.replace("mmHg", "").replace("mm Hg", "").strip().split("/")
        if len(parts) == 2:
            try:
                return {"systolic": float(parts[0].strip()), "diastolic": float(parts[1].strip())}
            except ValueError:
                return None
        return None
