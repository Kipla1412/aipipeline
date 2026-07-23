import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

"""
base.py
====================================
Purpose:
    Defines the abstract interface for all knowledge base generators.
"""

class BaseGenerator(ABC):
    """
    Purpose:
        Abstract base class that enforces a 'generate' method for all
        medical knowledge base generation strategies (Wiki, Report, etc.).
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def generate(self, document: Dict[str, Any], source_filename: str) -> List[Path]:
        """
        Purpose:
            Generates knowledge base pages from a structured medical document.

        Args:
            document (Dict[str, Any]): Structured MedicalDocument dict.
            source_filename (str): Original source filename for reference.

        Returns:
            List[Path]: Paths to all generated files.

        Raises:
            NotImplementedError: If the subclass does not implement this method.
        """
        raise NotImplementedError("Subclasses must implement generate()")
