"""ObservationNormalizer — standardizes observations post-extraction.

Responsibilities:
  - Remove duplicate observations
  - Normalize display names (e.g., 'Body Temperature' → 'Temperature')
  - Fix duplicated units (e.g., 'kg kg' → 'kg', 'cm cm' → 'cm')
  - Fix None units (e.g., 'None' → None)
  - Standardize interpretation values
  - Fix BMI unit
"""

from __future__ import annotations

from typing import Any

from ..interfaces import IObservationNormalizer


_NAME_NORMALIZATION: dict[str, str] = {
    "body temperature": "Temperature",
    "body weight": "Weight",
    "body height": "Height",
}


class ObservationNormalizer(IObservationNormalizer):
    def normalize(self, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: dict[str, int] = {}
        result: list[dict[str, Any]] = []

        for obs in observations:
            obs = self._normalize_name(obs)
            obs = self._normalize_value_suffix(obs)
            obs = self._normalize_unit(obs)
            obs = self._normalize_interpretation(obs)
            obs = self._fix_bmi_unit(obs)

            key = obs["display_name"].strip().lower()
            if key in seen:
                continue
            seen[key] = 1
            result.append(obs)

        return result

    @staticmethod
    def _normalize_name(obs: dict[str, Any]) -> dict[str, Any]:
        name = obs.get("display_name", "").strip()
        lower = name.lower()
        if lower in _NAME_NORMALIZATION:
            obs["display_name"] = _NAME_NORMALIZATION[lower]
        elif name == lower and name:
            obs["display_name"] = name.title()
        return obs

    @staticmethod
    def _normalize_unit(obs: dict[str, Any]) -> dict[str, Any]:
        unit = obs.get("unit")
        if unit is None or unit == "None" or unit == "":
            obs["unit"] = None
            return obs
        unit_str = str(unit).strip()
        parts = unit_str.split()
        if len(parts) >= 2 and parts[0] == parts[-1]:
            obs["unit"] = parts[0]
        elif unit_str.lower() == "none":
            obs["unit"] = None
        return obs

    @staticmethod
    def _normalize_value_suffix(obs: dict[str, Any]) -> dict[str, Any]:
        """Strip unit suffix from value string if it's already in the unit field."""
        unit = obs.get("unit")
        value = obs.get("value")
        if not unit or not isinstance(value, str):
            return obs
        unit_str = str(unit)
        value_str = str(value)
        if value_str.endswith(unit_str):
            obs["value"] = value_str[: -len(unit_str)].strip()
        elif unit_str in value_str and " " in value_str:
            parts = value_str.rsplit(unit_str, 1)
            obs["value"] = parts[0].strip()
        return obs

    @staticmethod
    def _normalize_interpretation(obs: dict[str, Any]) -> dict[str, Any]:
        interp = obs.get("interpretation")
        if interp is None:
            return obs
        interp_str = str(interp).strip().lower()
        valid = {"low", "normal", "high", "abnormal", "critical"}
        if interp_str in valid:
            obs["interpretation"] = interp_str
        elif interp_str == "none":
            obs["interpretation"] = None
        return obs

    @staticmethod
    def _fix_bmi_unit(obs: dict[str, Any]) -> dict[str, Any]:
        name = obs.get("display_name", "").strip().lower()
        if name == "bmi":
            unit = obs.get("unit")
            if unit is None or str(unit).lower() == "none" or str(unit).strip() == "":
                obs["unit"] = "kg/m²"
        return obs
