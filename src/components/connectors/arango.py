"""ArangoDBConnector — infrastructure component for ArangoDB connectivity.

Follows the same architecture as RDBMSConnector, RedisConnector, OpenSearchConnector:
  - Pydantic configuration validation
  - Client creation and authentication
  - Health check verification
  - Connection lifecycle management
  - Exposes database instance

Contains NO graph logic, NO vertex/edge insertion, NO business logic.
"""

from __future__ import annotations

import logging
from typing import Any

from arango import ArangoClient
from arango.database import StandardDatabase

from .schemas.arango import ArangoDBConfig

logger = logging.getLogger(__name__)


class ArangoDBConnector:
    def __init__(self, config: dict[str, Any]):
        """
        Purpose:
            Initializes the ArangoDBConnector with Pydantic-validated config.

        Args:
            config (dict): host, port, username, password, database, verify_certs.
        """
        self.config = ArangoDBConfig(**config)
        self._client: ArangoClient | None = None
        self._db: StandardDatabase | None = None
        logger.debug("ArangoDBConnector initialized for host: %s", self.config.host)

    def __call__(self) -> StandardDatabase:
        """
        Purpose:
            Connects to ArangoDB and returns the database handle.

        Returns:
            StandardDatabase: Connected ArangoDB database.
        """
        self.connect()
        return self._db

    def connect(self) -> None:
        """
        Purpose:
            Establishes ArangoDB connection with TLS, auth, and health check.

        Raises:
            ConnectionError: If ArangoDB is unreachable or authentication fails.
        """
        host = self.config.host
        host = host.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
        protocol = "https" if self.config.verify_certs else "http"
        url = f"{protocol}://{host}:{self.config.port}"

        logger.info("URL=%s  DB=%s  USER=%s  VERIFY=%s", url, self.config.database, self.config.username, self.config.verify_certs)

        try:
            self._client = ArangoClient(hosts=url)

            self._db = self._client.db(
                self.config.database,
                username=self.config.username,
                password=self.config.password,
                verify=self.config.verify_certs,
            )

            self._db.properties()
            logger.info("ArangoDB connection verified (database: %s)", self.config.database)

        except Exception as exc:
            logger.exception("Failed to establish ArangoDB connection")
            raise ConnectionError(f"ArangoDB connection failed: {exc}") from exc

    def close(self) -> None:
        """
        Purpose:
            Closes the ArangoDB connection and releases resources.
        """
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("ArangoDB connection closed")
