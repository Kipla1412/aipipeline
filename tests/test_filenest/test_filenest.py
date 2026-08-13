"""Tests for FileNest connector and read/download-only downloader.

Uses mocked FileNest SDK — no real credentials required.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from src.components.connectors.filenest import FileNestConnector
from src.components.connectors.schemas.filenest import FileNestConfig
from src.components.extractors.filenest import FileNestDownloader

CONFIG = {
    "api_key": "test-api-key",
    "project_id": "test-project",
    "base_url": "https://filenest.test",
}


def _install_filenest_mock():
    """Install a fake filenest module into sys.modules for lazy-import patches."""
    if "filenest" not in sys.modules:
        fake_module = MagicMock()
        fake_module.FileNest = MagicMock()
        sys.modules["filenest"] = fake_module
    return sys.modules["filenest"]


# ── A. Connector ──

class TestFileNestConnector:
    def test_valid_config_creates_client(self):
        fake = _install_filenest_mock()
        with patch("filenest.FileNest") as mock_fn:
            connector = FileNestConnector(CONFIG)
            client = connector()
            mock_fn.assert_called_once_with(
                api_key="test-api-key",
                project_id="test-project",
                base_url="https://filenest.test",
            )
            assert client is not None

    def test_requires_api_key(self):
        with pytest.raises(Exception):
            FileNestConfig(project_id="x", base_url="http://x")

    def test_close_releases_client(self):
        _install_filenest_mock()
        with patch("filenest.FileNest"):
            connector = FileNestConnector(CONFIG)
            connector()
            connector.close()
            assert connector._client is None


# ── B. list_files ──

class TestListFiles:
    def test_list_files_calls_sdk(self):
        connector = MagicMock()
        mock_files = [
            MagicMock(
                id="76775c3b-cd05-4f21-a56c-5b16a9054e3f",
                filename="Sample_CBC_Report.pdf",
                content_type="application/pdf",
                size_bytes=15571,
                status="ready",
                metadata={"serviceRequestId": 80002},
            )
        ]
        connector().files.list.return_value = mock_files

        downloader = FileNestDownloader(connector, {"download_dir": "storage/temp"})
        files = downloader.list_files()

        connector().files.list.assert_called_once()
        assert len(files) == 1
        assert files[0].id == "76775c3b-cd05-4f21-a56c-5b16a9054e3f"
        assert files[0].filename == "Sample_CBC_Report.pdf"

    def test_list_files_raises_on_error(self):
        connector = MagicMock()
        connector().files.list.side_effect = Exception("API down")
        downloader = FileNestDownloader(connector, {"download_dir": "storage/temp"})
        with pytest.raises(RuntimeError):
            downloader.list_files()


# ── C. get_file ──

class TestGetFile:
    def test_get_file_calls_sdk(self):
        connector = MagicMock()
        mock_file = MagicMock(id="abc-123", filename="check.pdf", status="ready")
        connector().files.get.return_value = mock_file

        downloader = FileNestDownloader(connector, {"download_dir": "storage/temp"})
        result = downloader.get_file("abc-123")

        connector().files.get.assert_called_once_with("abc-123")
        assert result.id == "abc-123"

    def test_get_file_not_found_raises(self):
        connector = MagicMock()
        connector().files.get.return_value = None
        downloader = FileNestDownloader(connector, {"download_dir": "storage/temp"})
        with pytest.raises(FileNotFoundError):
            downloader.get_file("missing-id")


# ── D. get_download_url ──

class TestGetDownloadUrl:
    def test_get_download_url_calls_sdk(self):
        connector = MagicMock()
        connector().files.get_download_url.return_value = MagicMock(
            url="https://filenest.test/download/signed-url"
        )
        downloader = FileNestDownloader(connector, {"download_dir": "storage/temp"})

        url = downloader.get_download_url("abc-123", ttl=3600)

        connector().files.get_download_url.assert_called_once_with("abc-123", ttl=3600)
        assert url == "https://filenest.test/download/signed-url"


# ── E. download_to_temp ──

class TestDownloadToTemp:
    def test_download_to_temp_writes_file(self, tmp_path):
        connector = MagicMock()
        connector().files.get.return_value = MagicMock(
            id="abc-123", filename="Sample_CBC_Report.pdf"
        )
        connector().files.get_download_url.return_value = MagicMock(
            url="https://filenest.test/download/signed-url"
        )

        downloader = FileNestDownloader(connector, {"download_dir": str(tmp_path)})

        with patch("httpx.Client") as mock_http:
            mock_http.return_value.__enter__.return_value.get.return_value = MagicMock(
                status_code=200,
                raise_for_status=MagicMock(),
                content=b"%PDF-1.4 fake content",
            )
            result = downloader.download_to_temp("abc-123")

        assert isinstance(result, Path)
        assert result.exists()
        assert result.name == "Sample_CBC_Report.pdf"
        assert result.read_bytes() == b"%PDF-1.4 fake content"

    def test_download_to_temp_uses_metadata_filename(self, tmp_path):
        connector = MagicMock()
        connector().files.get.return_value = MagicMock(
            id="abc-123", filename="PK0016.pdf"
        )
        connector().files.get_download_url.return_value = MagicMock(
            url="https://filenest.test/download/signed-url"
        )
        downloader = FileNestDownloader(connector, {"download_dir": str(tmp_path)})

        with patch("httpx.Client") as mock_http:
            mock_http.return_value.__enter__.return_value.get.return_value = MagicMock(
                raise_for_status=MagicMock(), content=b"data"
            )
            result = downloader.download_to_temp("abc-123")

        assert result.name == "PK0016.pdf"
        connector().files.get.assert_called_once_with("abc-123")

    def test_download_http_error_raises(self, tmp_path):
        connector = MagicMock()
        connector().files.get.return_value = MagicMock(
            id="abc-123", filename="x.pdf"
        )
        connector().files.get_download_url.return_value = MagicMock(
            url="https://filenest.test/download/signed-url"
        )
        downloader = FileNestDownloader(connector, {"download_dir": str(tmp_path)})

        import httpx
        with patch("httpx.Client") as mock_http:
            mock_http.return_value.__enter__.return_value.get.side_effect = httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock()
            )
            with pytest.raises(RuntimeError):
                downloader.download_to_temp("abc-123")

    def test_no_upload_method(self):
        """The downloader must NOT expose an upload method."""
        connector = MagicMock()
        downloader = FileNestDownloader(connector, {"download_dir": "storage/temp"})
        assert not hasattr(downloader, "upload")
