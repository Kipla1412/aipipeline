"""Graph repository layer — persistence backends for the Domain Graph model.

Each repository implements BaseGraphRepository and consumes a Graph object
returned by GraphBuilder. Repositories are interchangeable via ABC.

Available: JsonGraphRepository (file), ArangoGraphRepository (cloud),
Neo4jGraphRepository (local/cloud).
"""

from .base import BaseGraphRepository
from .json_repository import JsonGraphRepository
from .arango_repository import ArangoGraphRepository
from .neo4j_repository import Neo4jGraphRepository

__all__ = ["BaseGraphRepository", "JsonGraphRepository", "ArangoGraphRepository", "Neo4jGraphRepository"]
