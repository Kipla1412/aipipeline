import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

"""
factory.py
====================================
Purpose:
    Provides a universal entry point for creating specific transformer instances.
"""

class TransformerFactory:
    _transformers: dict[str, tuple[str, str]] = {
        "document": ("document", "DocumentTransformer"),
        "json": ("json_transformer", "JsonTransformer"),
        "chunker": ("arxiv", "TextChunker"),
        "pdf": ("arxiv", "PDFTransformer"),
        "medical_classifier": ("medical_classifier", "MedicalClassifier"),
        "medical": ("medical_transformer", "MedicalTransformer"),
    }
    _loaded: dict[str, type] = {}

    @staticmethod
    def get_transformer(transformer_type: str, data: Any | None = None, config: Dict[str, Any] | None = None):
        logger.info(f"TransformerFactory creating transformer for type: {transformer_type}")
        transformer_type = transformer_type.lower().strip()

        if transformer_type not in TransformerFactory._transformers:
            raise ValueError(f"Unknown transformer type: {transformer_type}")

        if transformer_type not in TransformerFactory._loaded:
            mod_name, cls_name = TransformerFactory._transformers[transformer_type]
            mod = __import__(f"src.components.transformers.{mod_name}", fromlist=[cls_name])
            TransformerFactory._loaded[transformer_type] = getattr(mod, cls_name)

        if transformer_type in ("medical_classifier", "medical"):
            return TransformerFactory._loaded[transformer_type](config=config or {})
        return TransformerFactory._loaded[transformer_type](data, config or {})
