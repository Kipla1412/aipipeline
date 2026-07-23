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

    async def transform(self, raw_text: str) -> Dict[str, Any]:
        response = await self.llm.generate(
            system_prompt=self._system_prompt,
            user_query=raw_text,
            response_format=MedicalSchema,
        )
        parsed = json.loads(response)
        result = self.clean(parsed)
        self._normalize_sections(result)
        return result

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
