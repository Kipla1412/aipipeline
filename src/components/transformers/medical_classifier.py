"""LLM-based report type classifier — standalone, no aipipeline dependency.

Uses LLMClient + embedded system prompt to classify medical document type.
"""

import json
import logging
import asyncio

from ..utils.llm import LLMClient

logger = logging.getLogger(__name__)

_CLASSIFY_PROMPT = """# Medical Report Classification System

You are a Medical Document Classifier.

Given the beginning of a medical document, identify its report type.

---

## Supported Report Types

Return a JSON object with a single key `report_type` whose value is one of:

- `mri` — MRI reports, sequences (T1, T2, STIR, FLAIR), anatomical findings
- `ct` — CT scans, contrast protocols, cross-sectional imaging
- `xray` — X-ray radiographs, chest X-ray, bone films
- `ultrasound` — Sonography, echocardiogram, Doppler studies
- `ecg` — ECG/EKG reports, rhythm strips, PR/QRS/QT intervals
- `blood_report` — CBC, blood panels, hematology with reference ranges
- `lab_report` — Urinalysis, metabolic panels, chemistry, non-blood labs
- `prescription` — Medication prescriptions, dosage instructions, drug lists
- `discharge_summary` — Hospital discharge, admission dates, hospital course
- `consultation` — Specialist consult notes, referrals, assessments
- `operative_report` — Surgical procedure notes, operative findings
- `histopathology` — Tissue pathology, biopsy, specimen examination
- `microbiology` — Culture results, sensitivity panels, organism identification
- `other` — Cannot determine type or does not match any category

---

## Classification Rules

1. **Lab values with reference ranges** → `blood_report`
2. **ECG measurements** (PR interval, QRS duration, QT interval) → `ecg`
3. **MRI sequences mentioned** (T1-weighted, T2-weighted, STIR, FLAIR) → `mri`
4. **CT-specific terms** (Hounsfield units, axial/sagittal cuts) → `ct`
5. **X-ray specific** (PA view, lateral view) → `xray`
6. **Medication lists with dosage** → `prescription`
7. **Admission date, discharge date, hospital course** → `discharge_summary`
8. **Surgical procedure, anesthesia, operative findings** → `operative_report`
9. **Specimen, gross description, microscopic examination** → `histopathology`
10. **Organism identification, sensitivity panel** → `microbiology`
11. If uncertain, return `other`

---

Return ONLY valid JSON. No explanation.
```json
{"report_type": "blood_report"}
```
"""


class MedicalClassifier:
    """Uses LLMClient to classify medical document type from document text."""

    def __init__(self, config: dict):
        """
        Purpose:
            Initializes the MedicalClassifier with LLM config.

        Args:
            config (dict): api_key, model, optional base_url.
        """
        self.config = config
        api_key = config.get("api_key", "")
        model = config.get("model", "gpt-4o-mini")
        base_url = config.get("base_url")
        self.llm = LLMClient(api_key=api_key, model=model, base_url=base_url)
        logger.info(f"MedicalClassifier initialized — model={model}")

    async def classify(self, text: str) -> str:
        """
        Purpose:
            Classifies a medical document's report type from text.

        Args:
            text: Extracted document text.

        Returns:
            str: Report type (mri, ct, xray, blood_report, other, etc.).
        """
        if not text.strip():
            return "other"
        sample = text[:800]
        try:
            response = await self.llm.generate(
                system_prompt=_CLASSIFY_PROMPT,
                user_query=sample,
                json_mode=True,
            )
            data = json.loads(response)
            report_type = data.get("report_type", "other")
            logger.info(f"Classified report as: {report_type}")
            return report_type
        except Exception as e:
            logger.warning(f"Classification failed, falling back to other: {e}")
            return "other"
