"""Pydantic configuration models for all connectors.

Each connector type has its own config model.
Import directly:

    from src.components.connectors.schemas import ArangoDBConfig, Neo4jConfig
"""

from .elasticsearch import ElasticsearchConfig
from .opensearch import OpensearchConfig
from .rdbms import RDBMSConfig
from .gmail import GmailConfig
from .arxiv import ArxivConfig
from .jina import JinaConfig
from .api import ApiConfig
from .s3 import S3Config
from .arango import ArangoDBConfig
from .neo4j import Neo4jConfig

__all__ = [
    "ElasticsearchConfig",
    "OpensearchConfig",
    "RDBMSConfig",
    "GmailConfig",
    "ArxivConfig",
    "JinaConfig",
    "ApiConfig",
    "S3Config",
    "ArangoDBConfig",
    "Neo4jConfig",
]