import logging
from typing import Any

from .base import BaseConnector

logger = logging.getLogger(__name__)

"""
connector_factory.py
====================================
Purpose:
    Implementation of the Factory pattern to route requests to specific 
    connector classes based on a string identifier.
"""

class ConnectorFactory:
    _connectors: dict[str, str] = {
        "rdbms": "RDBMSConnector",
        "gmail": "GmailConnector",
        "arxiv": "ArxivConnector",
        "elasticsearch": "ElasticsearchConnector",
        "opensearch": "OpensearchConnector",
        "jina": "JinaConnector",
        "s3": "S3Connector",
        "nas": "NASConnector",
        "arango": "ArangoDBConnector",
        "neo4j": "Neo4jConnector",
    }
    _loaded: dict[str, type] = {}

    @classmethod
    def get_connector(cls, connector_type: str, config: Any):
        logger.info(f"Factory creating connector for: {connector_type}")
        connector_type = connector_type.lower().strip()

        if connector_type not in cls._connectors:
            raise ValueError(f"Unknown connector type: {connector_type}")

        if connector_type not in cls._loaded:
            mod_name = connector_type
            try:
                mod = __import__(f"src.components.connectors.{mod_name}", fromlist=[cls._connectors[connector_type]])
                cls._loaded[connector_type] = getattr(mod, cls._connectors[connector_type])
            except ImportError as e:
                raise ImportError(f"Failed to load connector '{connector_type}': {e}") from e

        return cls._loaded[connector_type](config=config)
