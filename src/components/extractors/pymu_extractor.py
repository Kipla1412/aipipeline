import logging
from pathlib import Path
from typing import Dict, Any, Optional

import fitz
from .schemas.medical_extractor_configs import PyMuPdfExtractorConfig
from .schemas.extract_result import ExtractResult
from .base import BaseExtractor

logger = logging.getLogger(__name__)


class PyMuPdfExtractor(BaseExtractor):
    """Extracts markdown text and embedded images from medical PDF reports using PyMuPDF."""

    def __init__(self, config: Dict[str, Any]):
        self.config = PyMuPdfExtractorConfig(**config)
        self._doc: Optional[fitz.Document] = None

    def extract(self, pdf_path: str) -> ExtractResult:
        self._doc = fitz.open(pdf_path)
        logger.info(f"Opened PDF: {pdf_path} — {len(self._doc)} pages")

        markdown_parts = []
        images = []
        image_count = 0

        for page in self._doc:
            page_text = page.get_text("text")
            if page_text:
                markdown_parts.append(page_text)
            if not self.config.extract_images:
                continue
            for img in page.get_images(full=True):
                base_image = self._doc.extract_image(img[0])
                if not base_image:
                    continue
                image_bytes = base_image["image"]
                ext = base_image["ext"]
                image_count += 1
                image_filename = f"{Path(pdf_path).stem}_image_{image_count}.{ext}"
                image_path = Path(self.config.output_image_dir) / image_filename
                image_path.parent.mkdir(parents=True, exist_ok=True)
                image_path.write_bytes(image_bytes)
                images.append(str(image_path))

        self._doc.close()
        self._doc = None
        markdown = "\n\n".join(markdown_parts)
        logger.info(f"Extraction complete — {len(markdown)} chars, {len(images)} images")
        return ExtractResult(markdown=markdown, images=images)
