import logging

"""
Connectors Package
==================
Purpose:
    A unified interface for connecting to data sources.

Only the connectors used by this pipeline are eagerly imported:
RDBMS (PostgreSQL), FileNest (file storage), ArangoDB (graph), Neo4j (graph).
Other connectors (gmail, arxiv, elasticsearch, ...) are available via
ConnectorFactory but are NOT imported here, so their heavy dependencies
are only needed when actually used.
"""

# Import the Factory and connectors used by this pipeline
from .factory import ConnectorFactory
from .rdbms import RDBMSConnector
from .filenest import FileNestConnector
from .arango import ArangoDBConnector
from .neo4j import Neo4jConnector

# Define the public API for the package
__all__ = [
    "ConnectorFactory",
    "RDBMSConnector",
    "FileNestConnector",
    "ArangoDBConnector",
    "Neo4jConnector",
]

# Set a default logger for the package to prevent "No handler found" warnings
logging.getLogger(__name__).addHandler(logging.NullHandler())
