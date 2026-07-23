import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

"""
base.py
====================================
Purpose:
    Defines the abstract interface for knowledge graph builders.
"""

class BaseGraphBuilder(ABC):
    """
    Purpose:
        Abstract base class that enforces graph construction methods
        for medical knowledge graph generation.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def build_from_documents(self, documents: List[Dict[str, Any]], source_filename: str = "") -> Path:
        """
        Purpose:
            Builds a knowledge graph from structured MedicalDocument dicts.

        Args:
            documents: List of MedicalDocument dicts.
            source_filename: Original source file reference.

        Returns:
            Path: Path to the generated graph.json.

        Raises:
            NotImplementedError: If the subclass does not implement this method.
        """
        raise NotImplementedError("Subclasses must implement build_from_documents()")
