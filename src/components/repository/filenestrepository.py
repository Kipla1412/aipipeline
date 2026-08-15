"""FileNestRepository — PostgreSQL persistence for FileNest file records.

Responsibilities (database operations only):
  - save()                          upsert a FileNest file record
  - get_by_file_id()                lookup by unique FileNest ID
  - exists()                        check whether a FileNest ID is registered
  - update_download_status()        transition download state, set downloaded_at
  - get_pending_files()             files waiting to be downloaded
  - close()                         release the underlying connection

Uses the existing RDBMSConnector (dependency injection). No FileNest API calls,
no Airflow, no processing logic — persistence only.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import text

from ..connectors.rdbms import RDBMSConnector
from .models import DownloadStatus, FileNestFileRecord

logger = logging.getLogger(__name__)

_CREATE_TABLE_PG = """
CREATE TABLE IF NOT EXISTS filenest_files (
    id                SERIAL PRIMARY KEY,
    filenest_file_id  VARCHAR(64)  NOT NULL UNIQUE,
    filename          VARCHAR(512) NOT NULL,
    filepath          VARCHAR(1024),
    content_type      VARCHAR(128),
    size_bytes        BIGINT,
    filenest_status   VARCHAR(32),
    metadata          JSONB DEFAULT '{}'::jsonb,
    download_status   VARCHAR(32)  NOT NULL DEFAULT 'pending',
    downloaded_at     TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_filenest_download_status
    ON filenest_files (download_status);
"""

_CREATE_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS filenest_files (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    filenest_file_id  VARCHAR(64)  NOT NULL UNIQUE,
    filename          VARCHAR(512) NOT NULL,
    filepath          VARCHAR(1024),
    content_type      VARCHAR(128),
    size_bytes        BIGINT,
    filenest_status   VARCHAR(32),
    metadata          TEXT DEFAULT '{}',
    download_status   VARCHAR(32)  NOT NULL DEFAULT 'pending',
    downloaded_at     TIMESTAMP,
    created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_INDEX_SQLITE = """
CREATE INDEX IF NOT EXISTS idx_filenest_download_status
    ON filenest_files (download_status);
"""

_INSERT_SQL = """
INSERT INTO filenest_files (
    filenest_file_id, filename, filepath, content_type, size_bytes,
    filenest_status, metadata, download_status, created_at, updated_at
) VALUES (
    :filenest_file_id, :filename, :filepath, :content_type, :size_bytes,
    :filenest_status, :metadata, :download_status, :now, :now
)
ON CONFLICT (filenest_file_id) DO UPDATE SET
    filename        = EXCLUDED.filename,
    filepath        = EXCLUDED.filepath,
    content_type    = EXCLUDED.content_type,
    size_bytes      = EXCLUDED.size_bytes,
    filenest_status = EXCLUDED.filenest_status,
    metadata        = EXCLUDED.metadata,
    download_status = EXCLUDED.download_status,
    updated_at      = EXCLUDED.updated_at
RETURNING id, filenest_file_id, filename, filepath, content_type,
          size_bytes, filenest_status, metadata, download_status,
          downloaded_at, created_at, updated_at
"""

_SELECT_BY_FILE_ID_SQL = """
SELECT id, filenest_file_id, filename, filepath, content_type, size_bytes,
       filenest_status, metadata, download_status, downloaded_at, created_at, updated_at
FROM filenest_files
WHERE filenest_file_id = :filenest_file_id
"""

_EXISTS_SQL = """
SELECT 1 FROM filenest_files WHERE filenest_file_id = :filenest_file_id
"""

_UPDATE_STATUS_SQL = """
UPDATE filenest_files
SET download_status = :download_status,
    downloaded_at   = CASE WHEN :download_status = 'downloaded' THEN :downloaded_at ELSE downloaded_at END,
    updated_at      = :updated_at
WHERE filenest_file_id = :filenest_file_id
"""

_PENDING_SQL = """
SELECT id, filenest_file_id, filename, filepath, content_type, size_bytes,
       filenest_status, metadata, download_status, downloaded_at, created_at, updated_at
FROM filenest_files
WHERE download_status = 'pending'
ORDER BY id
"""

_ALL_SQL = """
SELECT id, filenest_file_id, filename, filepath, content_type, size_bytes,
       filenest_status, metadata, download_status, downloaded_at, created_at, updated_at
FROM filenest_files
ORDER BY id
"""


class FileNestRepository:
    """
    Purpose:
        Persists FileNest file metadata and download state to PostgreSQL.

    Args:
        connector (RDBMSConnector): Pre-configured SQLAlchemy connector.
    """

    def __init__(self, connector: RDBMSConnector):
        self._connector = connector
        self._tables_ready = False

    # ── Public API ──

    def save(self, record: FileNestFileRecord) -> FileNestFileRecord:
        """
        Purpose:
            Upserts a FileNest file record into PostgreSQL.

        Args:
            record (FileNestFileRecord): Record to persist.

        Returns:
            FileNestFileRecord: The stored record with DB-assigned fields.
        """
        with self._connection() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                text(_INSERT_SQL),
                self._params(record),
            ).mappings().one_or_none()
            self._commit(conn)
        logger.info("Saved FileNest record: %s", record.filenest_file_id)
        return self._row_to_record(row)

    def get_by_file_id(self, file_id: str) -> FileNestFileRecord | None:
        """
        Purpose:
            Retrieves a record by its unique FileNest ID.

        Args:
            file_id (str): FileNest file ID.

        Returns:
            FileNestFileRecord | None: The record, or None if not found.
        """
        with self._connection() as conn:
            self._ensure_tables(conn)
            row = conn.execute(
                text(_SELECT_BY_FILE_ID_SQL),
                {"filenest_file_id": file_id},
            ).mappings().one_or_none()
        if row is None:
            return None
        return self._row_to_record(row)

    def exists(self, file_id: str) -> bool:
        """
        Purpose:
            Checks whether a FileNest file ID is already registered.

        Args:
            file_id (str): FileNest file ID.

        Returns:
            bool: True if the ID exists in PostgreSQL, False otherwise.
        """
        with self._connection() as conn:
            self._ensure_tables(conn)
            row = conn.execute(text(_EXISTS_SQL), {"filenest_file_id": file_id}).fetchone()
        return row is not None

    def update_download_status(self, file_id: str, status: DownloadStatus) -> None:
        """
        Purpose:
            Updates the application download state for a file.

        Args:
            file_id (str): FileNest file ID.
            status (DownloadStatus): pending | downloading | downloaded | failed.

        Raises:
            ValueError: If no record exists for the given file ID.
        """
        with self._connection() as conn:
            self._ensure_tables(conn)
            now = datetime.now(timezone.utc)
            result = conn.execute(
                text(_UPDATE_STATUS_SQL),
                {
                    "filenest_file_id": file_id,
                    "download_status": status.value,
                    "downloaded_at": now,
                    "updated_at": now,
                },
            )
            if result.rowcount == 0:
                raise ValueError(f"No FileNest record found for file_id: {file_id}")
            self._commit(conn)
        logger.info("Updated download_status=%s for %s", status.value, file_id)

    def get_pending_files(self) -> list[FileNestFileRecord]:
        """
        Purpose:
            Returns all files whose download_status is 'pending'.

        Returns:
            list[FileNestFileRecord]: Pending files.
        """
        with self._connection() as conn:
            self._ensure_tables(conn)
            rows = conn.execute(text(_PENDING_SQL)).mappings().all()
        return [self._row_to_record(r) for r in rows]

    def list_all(self) -> list[FileNestFileRecord]:
        """
        Purpose:
            Returns all stored FileNest file records regardless of status.

        Returns:
            list[FileNestFileRecord]: All records ordered by id.
        """
        with self._connection() as conn:
            self._ensure_tables(conn)
            rows = conn.execute(text(_ALL_SQL)).mappings().all()
        return [self._row_to_record(r) for r in rows]

    def close(self) -> None:
        """
        Purpose:
            Releases the underlying database connection.
        """
        try:
            if hasattr(self._connector, "close"):
                self._connector.close()
        except Exception as exc:  # pragma: no cover
            logger.warning("Error closing connector: %s", exc)

    # ── Internals ──

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        """Context manager: opens a connection, closes it on exit."""
        conn = self._connector()
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_tables(self, conn) -> None:
        if self._tables_ready:
            return
        dialect = conn.dialect.name
        if dialect == "postgresql":
            conn.execute(text(_CREATE_TABLE_PG))
        else:
            conn.execute(text(_CREATE_TABLE_SQLITE))
            conn.execute(text(_CREATE_INDEX_SQLITE))
        self._commit(conn)
        self._tables_ready = True

    @staticmethod
    def _commit(conn) -> None:
        """Commit — compatible with SQLAlchemy 1.4 (no Connection.commit) and 2.0."""
        if hasattr(conn, "commit"):
            conn.commit()
        else:
            conn.execute(text("COMMIT"))

    @staticmethod
    def _params(record: FileNestFileRecord) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "filenest_file_id": record.filenest_file_id,
            "filename": record.filename,
            "filepath": record.filepath,
            "content_type": record.content_type,
            "size_bytes": record.size_bytes,
            "filenest_status": record.filenest_status,
            "metadata": json.dumps(record.metadata or {}),
            "download_status": record.download_status.value,
            "now": now,
        }

    @staticmethod
    def _row_to_record(row) -> FileNestFileRecord:
        if row is None:
            raise ValueError("Empty row")
        data = dict(row)
        metadata = data.get("metadata")
        if isinstance(metadata, str):
            metadata = json.loads(metadata or "{}")
        data["metadata"] = metadata or {}
        return FileNestFileRecord(**data)
