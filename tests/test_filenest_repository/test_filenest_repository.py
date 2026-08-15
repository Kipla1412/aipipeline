"""Unit tests for FileNestRepository — uses SQLite in-memory via the real RDBMSConnector.

No PostgreSQL or FileNest credentials required.
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Python 3.12 deprecated the default sqlite3 datetime adapter; register our own
# so datetimes bind cleanly to the SQLite test database.
import sqlite3

sqlite3.register_adapter(datetime, lambda dt: dt.isoformat(sep=" "))

import pytest

from src.components.connectors.rdbms import RDBMSConnector
from src.components.repository.models import DownloadStatus, FileNestFileRecord
from src.components.repository.filenestrepository import FileNestRepository


@pytest.fixture
def repo(tmp_path):
    """File-backed SQLite repository (in-memory :memory: resets per engine creation)."""
    db_path = tmp_path / "filenest_test.db"
    connector = RDBMSConnector({
        "type": "sqlite",
        "host": "localhost",
        "port": 0,
        "login": "",
        "password": None,
        "database": str(db_path),
    })
    r = FileNestRepository(connector)
    yield r
    r.close()


def make_record(
    file_id="76775c3b-cd05-4f21-a56c-5b16a9054e3f",
    filename="Sample_CBC_Report.pdf",
    **overrides,
) -> FileNestFileRecord:
    defaults = dict(
        filenest_file_id=file_id,
        filename=filename,
        filepath="storage/temp/Sample_CBC_Report.pdf",
        content_type="application/pdf",
        size_bytes=15571,
        filenest_status="ready",
        metadata={"serviceRequestId": 80002, "patientFhirId": 10000},
    )
    defaults.update(overrides)
    return FileNestFileRecord(**defaults)


# ── save() ──

class TestSave:
    def test_save_persists_record(self, repo):
        record = make_record()
        saved = repo.save(record)

        assert saved.id is not None
        assert saved.filenest_file_id == "76775c3b-cd05-4f21-a56c-5b16a9054e3f"
        assert saved.filename == "Sample_CBC_Report.pdf"
        assert saved.download_status == DownloadStatus.PENDING

    def test_save_duplicate_file_id_is_upsert(self, repo):
        """Same filenest_file_id twice → single row, fields updated (no duplicate)."""
        repo.save(make_record(filename="first.pdf", metadata={"a": 1}))
        repo.save(make_record(filename="second.pdf", metadata={"a": 2}))

        rows = repo.get_pending_files()
        assert len(rows) == 1  # no duplicate
        assert rows[0].filename == "second.pdf"
        assert rows[0].metadata == {"a": 2}


# ── get_by_file_id() ──

class TestGetByFileId:
    def test_returns_correct_record(self, repo):
        repo.save(make_record(file_id="abc-111", filename="check.pdf"))
        repo.save(make_record(file_id="abc-222", filename="other.pdf"))

        record = repo.get_by_file_id("abc-111")
        assert record is not None
        assert record.filename == "check.pdf"

    def test_returns_none_for_unknown(self, repo):
        assert repo.get_by_file_id("does-not-exist") is None


# ── exists() ──

class TestExists:
    def test_existing_file(self, repo):
        repo.save(make_record(file_id="abc-123"))
        assert repo.exists("abc-123") is True

    def test_unknown_file(self, repo):
        assert repo.exists("unknown-id") is False


# ── update_download_status() ──

class TestUpdateDownloadStatus:
    def test_transition_pending_downloading_downloaded(self, repo):
        repo.save(make_record(file_id="abc-123"))

        repo.update_download_status("abc-123", DownloadStatus.DOWNLOADING)
        record = repo.get_by_file_id("abc-123")
        assert record.download_status == DownloadStatus.DOWNLOADING
        assert record.downloaded_at is None

        repo.update_download_status("abc-123", DownloadStatus.DOWNLOADED)
        record = repo.get_by_file_id("abc-123")
        assert record.download_status == DownloadStatus.DOWNLOADED
        assert record.downloaded_at is not None  # set on download

    def test_update_unknown_file_raises(self, repo):
        with pytest.raises(ValueError):
            repo.update_download_status("missing", DownloadStatus.DOWNLOADED)

    def test_failed_status(self, repo):
        repo.save(make_record(file_id="abc-123"))
        repo.update_download_status("abc-123", DownloadStatus.FAILED)
        record = repo.get_by_file_id("abc-123")
        assert record.download_status == DownloadStatus.FAILED
        assert record.downloaded_at is None  # not set for failed


# ── get_pending_files() ──

class TestGetPendingFiles:
    def test_returns_only_pending(self, repo):
        repo.save(make_record(file_id="a", filename="a.pdf"))
        repo.save(make_record(file_id="b", filename="b.pdf"))
        repo.update_download_status("b", DownloadStatus.DOWNLOADED)
        repo.save(make_record(file_id="c", filename="c.pdf"))

        pending = repo.get_pending_files()
        ids = {r.filenest_file_id for r in pending}
        assert ids == {"a", "c"}
