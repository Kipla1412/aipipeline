from pydantic import BaseModel, Field
from pathlib import Path

"""
wiki.py
====================================
Purpose:
    Pydantic configuration model for the Wiki Generator component.
"""

class WikiGeneratorConfig(BaseModel):
    """
    Purpose:
        Validates and stores configuration for the patient-centric Wiki Generator.

    Mandatory Fields:
        base_dir (Path): Root directory for the wiki knowledge base output.
    """

    base_dir: Path = Field(
        default=Path("storage/wiki"),
        description="Root directory for wiki knowledge base output"
    )
