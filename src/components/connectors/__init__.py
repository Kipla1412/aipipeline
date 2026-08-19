import logging

"""
Connectors Package
==================
Purpose:
    A unified interface for connecting to data sources.

Only the connectors used by every pipeline are eagerly imported:
RDBMS (PostgreSQL) and FileNest (file storage).
Optional connectors (ArangoDB, Neo4j, gmail, arxiv, elasticsearch, ...)
are available via ConnectorFactory but are NOT imported here, so their
heavy dependencies are only needed when actually used.
"""

# Import the Factory and the core connectors used by every pipeline
from .factory import ConnectorFactory
from .rdbms import RDBMSConnector
from .filenest import FileNestConnector

# Define the public API for the package
__all__ = [
    "ConnectorFactory",
    "RDBMSConnector",
    "FileNestConnector",
]

# Set a default logger for the package to prevent "No handler found" warnings
logging.getLogger(__name__).addHandler(logging.NullHandler())
