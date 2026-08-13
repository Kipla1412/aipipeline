"""FileNestConnector — infrastructure component for FileNest cloud file storage.

Follows the same architecture as S3Connector, RDBMSConnector, ApiConnector:
  - Pydantic configuration validation
  - Client creation and authentication
  - Connection lifecycle management
  - Exposes the FileNest client

Contains NO file upload/download logic, NO business logic.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseConnector
from .schemas.filenest import FileNestConfig

logger = logging.getLogger(__name__)


class FileNestConnector(BaseConnector):
    """
    Purpose:
        Manages the lifecycle of a FileNest client connection.
        Handles configuration validation and authentication.

    Usage:
        connector = FileNestConnector(config_dict)
        client = connector()   # returns FileNest client
    """

    def __init__(self, config: dict[str, Any]):
        """
        Purpose:
            Initializes the FileNestConnector with validated config.

        Args:
            config (dict): api_key, project_id, base_url, optional timeout.
        """
        self.config = FileNestConfig(**config)
        self._client = None
        logger.debug("FileNestConnector initialized for project: %s", self.config.project_id)

    def __call__(self):
        """
        Purpose:
            Connects and returns the FileNest client instance.

        Returns:
            FileNest: Active FileNest client.
        """
        self.connect()
        return self._client

    def connect(self):
        """
        Purpose:
            Creates the FileNest client using configured credentials.

        Returns:
            FileNest: Active FileNest client.

        Raises:
            ImportError: If the filenest package is not installed.
            Exception: If client creation fails.
        """
        try:
            from filenest import FileNest
        except ImportError as exc:
            logger.exception("filenest package not installed. Run: pip install filenest")
            raise ImportError("filenest is required for FileNestConnector. Install: pip install filenest") from exc

        logger.info(
            "Connecting to FileNest (project=%s, base_url=%s)",
            self.config.project_id, self.config.base_url,
        )
        try:
            self._client = FileNest(
                api_key=self.config.api_key,
                project_id=self.config.project_id,
                base_url=self.config.base_url,
            )
            logger.info("FileNest client created successfully.")
        except Exception as exc:
            logger.exception("Failed to create FileNest client")
            raise ConnectionError(f"FileNest connection failed: {exc}") from exc

        return self._client

    def close(self) -> None:
        """
        Purpose:
            Releases the FileNest client resources.

        Args:
            None

        Returns:
            None
        """
        self._client = None
        logger.info("FileNest connection closed")
