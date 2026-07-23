import logging
from pathlib import Path
from typing import Any

from ..utils.llm import LLMClient
from .base import BaseExtractor
from .schemas.medical_extractor_configs import ImageAnalyzerConfig

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class ImageAnalyzer(BaseExtractor):
    def __init__(self, config: dict[str, Any]):
        validated = ImageAnalyzerConfig(**config)
        self.api_key = validated.api_key
        self.model = validated.model_name
        self._system_prompt = (_PROMPTS_DIR / "image_analysis.md").read_text(encoding="utf-8")

    async def extract(self, image_paths: list[str]) -> str:
        llm = LLMClient(api_key=self.api_key, model=self.model)
        descriptions: list[str] = []
        for img_path in image_paths:
            path = Path(img_path)
            if not path.exists():
                descriptions.append(f"[Image not available: {path.name}]")
                continue
            try:
                desc = await llm.describe_image(self._system_prompt, img_path)
                descriptions.append(f"[IMAGE: {path.name}]\n{desc}\n[/IMAGE]")
            except Exception as e:
                logger.error(f"Image analysis failed for {path.name}: {e}")
                descriptions.append(f"[Image could not be analyzed: {path.name}]")
        return "\n\n".join(descriptions)
