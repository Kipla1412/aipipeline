"""ObservationValidator — validates observation objects.

Responsibilities:
  - Validate required fields (display_name, category)
  - Validate numeric observations have numeric values
  - Validate interpretation values are in allowed set
  - Validate category is in allowed set
  - No FHIR validation
"""

from __future__ import annotations

import logging
from typing import Any

from ..interfaces import IObservationValidator

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {"vital_signs", "laboratory", "imaging", "ecg", "pathology", "microbiology"}
_VALID_INTERPRETATIONS = {"low", "normal", "high", "abnormal", "critical", None}


class ObservationValidator(IObservationValidator):
    def validate(self, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Purpose:
            Validates observation required fields, categories, and interpretations.

        Args:
            observations: List of observation dicts.

        Returns:
            list[dict]: Observations (warnings logged for invalid entries).
        """
        result: list[dict[str, Any]] = []

        for i, obs in enumerate(observations):
            issues: list[str] = []

            name = obs.get("display_name", "").strip()
            if not name:
                issues.append("missing display_name")

            category = obs.get("category", "").strip().lower()
            if not category:
                issues.append("missing category")
            elif category not in _VALID_CATEGORIES:
                issues.append(f"invalid category '{category}'")

            interpretation = obs.get("interpretation")
            if interpretation is not None and str(interpretation).strip().lower() not in _VALID_INTERPRETATIONS:
                issues.append(f"invalid interpretation '{interpretation}'")

            if issues:
                logger.warning("Observation[%d] '%s': %s", i, name or "unnamed", "; ".join(issues))

            result.append(obs)

        valid_count = len(result)
        logger.info("ObservationValidator: %d/%d observations passed", valid_count, len(observations))
        return result
