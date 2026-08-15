"""Application-level record for FileNest files persisted in PostgreSQL.

This is a DTO (data transfer object), not a SQLAlchemy ORM model.
The project uses raw SQLAlchemy connections (see RDBMSConnector), so the
repository maps these records to/from the `filenest_files` table.

`filenest_file_id` is the unique identity from the FileNest SDK —
NEVER use filename as a unique identifier (duplicate filenames are possible).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DownloadStatus(StrEnum):
    """Application download state for a FileNest file. Processing states are out of scope."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    FAILED = "failed"


class FileNestFileRecord(BaseModel):
    """A row in the `filenest_files` PostgreSQL table."""

    id: int | None = Field(None, description="Database primary key (assigned by DB)")
    filenest_file_id: str = Field(description="Unique FileNest file ID (identity)")
    filename: str = Field(description="Original filename from FileNest")
    filepath: str | None = Field(None, description="Local download path, e.g. storage/temp/x.pdf")
    content_type: str | None = Field(None, description="MIME type, e.g. application/pdf")
    size_bytes: int | None = Field(None, description="File size in bytes from FileNest")
    filenest_status: str | None = Field(None, description="Status from FileNest (ready, pending, ...)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Dynamic FileNest metadata (JSONB)")
    download_status: DownloadStatus = Field(default=DownloadStatus.PENDING)
    downloaded_at: datetime | None = Field(None, description="Set when download succeeds")
    created_at: datetime | None = Field(None, description="Record creation time (DB default now())")
    updated_at: datetime | None = Field(None, description="Record update time (DB default now())")
