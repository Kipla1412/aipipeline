"""FileNestDownloader — read/download-only operations for FileNest cloud storage.

Owned by an external application that handles uploads. This downloader only:
  - lists files
  - retrieves file metadata
  - generates temporary signed download URLs
  - downloads files into a local temporary staging folder (storage/temp)

Mirrors ArxivDownloader pattern (connector + file operations).
No upload logic, no processing state, no PostgreSQL, no Airflow.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FileNestDownloader:
    """
    Purpose:
        Read/download-only file operations against FileNest.
        Downloads land in a configurable temporary staging directory.

    Usage:
        downloader = FileNestDownloader(connector, {"download_dir": "storage/temp"})
        files = downloader.list_files()
        path = downloader.download_to_temp(file_id)
    """

    def __init__(self, connection: Any, config: dict[str, Any]):
        """
        Purpose:
            Initializes the FileNestDownloader with a shared connector client.

        Args:
            connection: FileNestConnector instance providing the SDK client.
            config (dict): Optional download_dir (defaults to 'storage/temp').
        """
        self.connection = connection
        self.client = connection()
        self.download_dir = Path(config.get("download_dir", "storage/temp"))
        self.download_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileNestDownloader initialized | Target: {self.download_dir}")

    def list_files(self) -> list[Any]:
        """
        Purpose:
            Lists existing files in FileNest.

        Returns:
            list[File]: FileNest file objects with id, filename, content_type,
                        size_bytes, status, folder_id, metadata, etc.

        Raises:
            Exception: If the FileNest list API call fails.
        """
        try:
            response = self.client.files.list()
            files = list(response.items)
            logger.info(f"FileNest list returned {len(files)} file(s) (total={response.total})")
            return files
        except Exception as exc:
            logger.exception("FileNest list failed")
            raise RuntimeError(f"FileNest list failed: {exc}") from exc

    def get_file(self, file_id: str) -> Any:
        """
        Purpose:
            Retrieves metadata for a single FileNest file.

        Args:
            file_id: FileNest unique file identifier.

        Returns:
            File: FileNest file object.

        Raises:
            FileNotFoundError: If the file does not exist in FileNest.
            Exception: If the FileNest API call fails.
        """
        try:
            file = self.client.files.get(file_id)
            if file is None:
                raise FileNotFoundError(f"FileNest file not found: {file_id}")
            logger.info(f"FileNest get returned file: {file.filename} ({file.id})")
            return file
        except FileNotFoundError:
            raise
        except Exception as exc:
            logger.exception(f"FileNest get failed for {file_id}")
            raise RuntimeError(f"FileNest get failed: {exc}") from exc

    def get_download_url(self, file_id: str, ttl: int = 3600) -> str:
        """
        Purpose:
            Generates a fresh temporary signed download URL for a file.

        Args:
            file_id: FileNest unique file identifier.
            ttl: URL time-to-live in seconds.

        Returns:
            str: Temporary signed download URL.

        Raises:
            Exception: If the FileNest API call fails.
        """
        try:
            dl = self.client.files.get_download_url(file_id, ttl=ttl)
            logger.info(f"Download URL generated for {file_id} (ttl={ttl}s)")
            return dl.url
        except Exception as exc:
            logger.exception(f"FileNest get_download_url failed for {file_id}")
            raise RuntimeError(f"FileNest get_download_url failed: {exc}") from exc

    def download_to_temp(
        self, file_id: str, filename: str | None = None, ttl: int = 3600
    ) -> Path:
        """
        Purpose:
            Downloads a FileNest file into the temporary staging folder.

        Args:
            file_id: FileNest unique file identifier.
            filename: Optional output filename; defaults to the FileNest filename.
            ttl: Download URL TTL in seconds.

        Returns:
            Path: Path to the downloaded file under storage/temp/.

        Raises:
            FileNotFoundError: If the file does not exist in FileNest.
            RuntimeError: If the download or filesystem write fails.
        """
        import httpx

        # Resolve the actual filename from FileNest metadata when not provided
        if filename is None:
            file_meta = self.get_file(file_id)
            filename = getattr(file_meta, "filename", None) or f"{file_id}"
            logger.info(f"Resolved filename from FileNest metadata: {filename}")

        url = self.get_download_url(file_id, ttl)

        target = self.download_dir / filename
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.get(url)
                resp.raise_for_status()
                target.write_bytes(resp.content)
        except httpx.HTTPError as exc:
            logger.exception(f"Download failed for {file_id}")
            raise RuntimeError(f"FileNest download failed: {exc}") from exc
        except OSError as exc:
            logger.exception(f"Filesystem write failed for {target}")
            raise RuntimeError(f"FileNest write to {target} failed: {exc}") from exc

        logger.info(f"Downloaded {file_id} → {target} ({target.stat().st_size} bytes)")
        return target

    def close(self) -> None:
        """
        Purpose:
            Releases the underlying connector client.

        Args:
            None

        Returns:
            None
        """
        self.connection.close()
