import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

"""
factory.py
====================================
Purpose:
    Simplifies the creation of Extractor objects.
"""

class ExtractorFactory:
    _extractors: dict[str, tuple[str, str]] = {
        "rdbms": ("rdbms", "RDBMSExtractor"),
        "gmail": ("gmail", "GmailExtractor"),
        "arxiv": ("arxiv", "ArxivExtractor"),
        "elasticsearch": ("elasticsearch", "ElasticsearchExtractor"),
        "opensearch": ("opensearch", "OpensearchExtractor"),
        "pdf": ("pymu_extractor", "PyMuPdfExtractor"),
        "dicom": ("dicom", "DicomExtractor"),
        "image": ("image_analyzer", "ImageAnalyzer"),
        "filenest": ("filenest", "FileNestDownloader"),
    }
    _loaded: dict[str, type] = {}

    @staticmethod
    def get_extractor(extractor_type: str, connection: Any | None = None, config: Dict[str, Any] | None = None):
        logger.info(f"ExtractorFactory generating '{extractor_type}' extractor.")
        extractor_type = extractor_type.lower().strip()

        if extractor_type not in ExtractorFactory._extractors:
            raise ValueError(f"Unknown extractor type: {extractor_type}")

        if extractor_type not in ExtractorFactory._loaded:
            mod_name, cls_name = ExtractorFactory._extractors[extractor_type]
            mod = __import__(f"src.components.extractors.{mod_name}", fromlist=[cls_name])
            ExtractorFactory._loaded[extractor_type] = getattr(mod, cls_name)

        if extractor_type in ("pdf", "image", "dicom"):
            return ExtractorFactory._loaded[extractor_type](config=config or {})
        return ExtractorFactory._loaded[extractor_type](connection=connection, config=config or {})
