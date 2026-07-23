from pydantic import BaseModel, Field

"""
graph.py
====================================
Purpose:
    Pydantic configuration model for the Graph Builder component.
"""

class GraphBuilderConfig(BaseModel):
    """
    Purpose:
        Validates and stores configuration for the Graphifyy knowledge graph builder.

    Mandatory Fields:
        target_dir (str): Root wiki directory for graph generation.
    """

    target_dir: str = Field(
        default="storage/wiki",
        description="Root wiki directory for graph node/edge generation"
    )
