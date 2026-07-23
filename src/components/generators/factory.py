import logging
from typing import Any, Dict

from .wiki_generator_wrapper import WikiGenerator

logger = logging.getLogger(__name__)

"""
factory.py
====================================
Purpose:
    Factory class to route requests to the correct Generator implementation.
"""

class GeneratorFactory:
    """
    Purpose:
        Factory class that selects the appropriate medical knowledge base
        generator based on type identifier.
    """

    @staticmethod
    def get_generator(generator_type: str, config: Dict[str, Any]):
        """
        Purpose:
            Instantiates the requested generator.

        Args:
            generator_type (str): Type of generator ('wiki').
            config (Dict[str, Any]): Configuration for the generator.

        Returns:
            BaseGenerator: An initialized generator instance.

        Raises:
            ValueError: If the generator_type is unsupported.
        """
        logger.info(f"GeneratorFactory creating generator for type: {generator_type}")
        generator_type = generator_type.lower().strip()

        if generator_type == "wiki":
            return WikiGenerator(config=config)
        else:
            error_msg = f"Unknown generator type: {generator_type}"
            logger.error(error_msg)
            raise ValueError(error_msg)
