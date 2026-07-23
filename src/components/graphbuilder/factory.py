import logging
from typing import Any, Dict

from .graphify_builder import GraphifyyBuilder

logger = logging.getLogger(__name__)

"""
factory.py
====================================
Purpose:
    Factory class to route requests to the correct Graph Builder implementation.
"""

class GraphBuilderFactory:
    """
    Purpose:
        Factory class that selects the appropriate knowledge graph builder
        based on type identifier.
    """

    @staticmethod
    def get_builder(builder_type: str, config: Dict[str, Any]):
        """
        Purpose:
            Instantiates the requested graph builder.

        Args:
            builder_type (str): Type of graph builder ('graphifyy').
            config (Dict[str, Any]): Configuration for the builder.

        Returns:
            BaseGraphBuilder: An initialized graph builder instance.

        Raises:
            ValueError: If the builder_type is unsupported.
        """
        logger.info(f"GraphBuilderFactory creating builder for type: {builder_type}")
        builder_type = builder_type.lower().strip()

        if builder_type == "graphifyy":
            return GraphifyyBuilder(config=config)
        else:
            error_msg = f"Unknown graph builder type: {builder_type}"
            logger.error(error_msg)
            raise ValueError(error_msg)
