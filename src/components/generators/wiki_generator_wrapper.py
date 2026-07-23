"""Concrete WikiGenerator — generates patient-centric medical knowledge base pages.

Wraps the self-contained WikiGenerator with the aiplatform component pattern
(BaseGenerator ABC + Pydantic config).
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseGenerator
from .schemas.wiki import WikiGeneratorConfig
from .wiki_generator import WikiGenerator as CoreWikiGen

logger = logging.getLogger(__name__)


class WikiGenerator(BaseGenerator):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        validated = WikiGeneratorConfig(**config)
        self._engine = CoreWikiGen(validated.base_dir)
        logger.info(f"WikiGenerator initialized — base_dir={validated.base_dir}")

    def generate(self, document: Dict[str, Any], source_filename: str = "") -> List[Path]:
        logger.info(f"Generating wiki for '{document.get('patient_name', 'Unknown')}' [{source_filename}]")
        paths = self._engine.generate(document, source_filename)
        logger.info(f"Wiki generation complete — {len(paths)} files")
        return paths
