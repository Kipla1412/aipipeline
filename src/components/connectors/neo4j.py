"""Neo4jConnector — infrastructure component for Neo4j connectivity.

Follows the same architecture as ArangoDBConnector, RDBMSConnector, RedisConnector:
  - Pydantic configuration validation
  - Client creation and authentication
  - Health check verification
  - Connection lifecycle management
  - Exposes database driver instance

Contains NO graph logic, NO node/relationship creation, NO business logic.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import GraphDatabase, Driver

from .schemas.neo4j import Neo4jConfig

logger = logging.getLogger(__name__)


class Neo4jConnector:
    def __init__(self, config: dict[str, Any]):
        """
        Purpose:
            Initializes the Neo4jConnector with Pydantic-validated config.

        Args:
            config (dict): uri, username, password, database.
        """
        self.config = Neo4jConfig(**config)
        self._driver: Driver | None = None
        logger.debug("Neo4jConnector initialized for uri: %s", self.config.uri)

    def __call__(self) -> Driver:
        """
        Purpose:
            Connects to Neo4j and returns the Driver instance.

        Returns:
            Driver: Connected Neo4j driver.
        """
        self.connect()
        return self._driver

    def connect(self) -> None:
        """
        Purpose:
            Establishes Neo4j connection and verifies connectivity.

        Raises:
            ConnectionError: If Neo4j is unreachable or authentication fails.
        """
        if self._driver is not None:
            return

        logger.info(
            "Connecting to Neo4j at %s (database=%s)",
            self.config.uri, self.config.database,
        )

        try:
            self._driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.username, self.config.password),
            )

            self._driver.verify_connectivity()
            logger.info(
                "Neo4j connection verified (database: %s)", self.config.database
            )

        except Exception as exc:
            logger.exception("Failed to establish Neo4j connection")
            raise ConnectionError(f"Neo4j connection failed: {exc}") from exc

    def close(self) -> None:
        """
        Purpose:
            Closes the Neo4j Driver connection.
        """
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")
