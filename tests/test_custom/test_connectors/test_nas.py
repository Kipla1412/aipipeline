import pytest
import asyncio
from pathlib import Path
from pydantic import ValidationError
from src.components.connectors.schemas.nasconfig import NASConfig
from src.components.connectors.nas import NASConnector, NASFileSystemSession


class TestNASConfig:
    def test_valid_config(self, tmp_path):
        config = NASConfig(nas_dir_path=str(tmp_path))
        assert str(config.nas_dir_path) == str(tmp_path)
        assert config.allowed_extensions == [".pdf"]

    def test_custom_extensions(self, tmp_path):
        config = NASConfig(nas_dir_path=str(tmp_path), allowed_extensions=[".txt", ".md"])
        assert config.allowed_extensions == [".txt", ".md"]

    def test_nonexistent_directory_raises(self):
        with pytest.raises(ValidationError):
            NASConfig(nas_dir_path="/no/such/dir/12345")


class TestNASFileSystemSession:
    def test_finds_pdf_files(self, tmp_path):
        (tmp_path / "report1.pdf").touch()
        (tmp_path / "report2.pdf").touch()
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "report3.pdf").touch()
        config = NASConfig(nas_dir_path=str(tmp_path))
        files = NASFileSystemSession(config).get_new_files()
        assert len(files) == 3

    def test_finds_only_allowed_extensions(self, tmp_path):
        (tmp_path / "report.pdf").touch()
        (tmp_path / "notes.txt").touch()
        config = NASConfig(nas_dir_path=str(tmp_path), allowed_extensions=[".pdf", ".txt"])
        files = NASFileSystemSession(config).get_new_files()
        assert len(files) == 2

    def test_extension_case_insensitive(self, tmp_path):
        (tmp_path / "report.PDF").touch()
        config = NASConfig(nas_dir_path=str(tmp_path))
        files = NASFileSystemSession(config).get_new_files()
        assert len(files) == 1

    def test_empty_directory(self, tmp_path):
        config = NASConfig(nas_dir_path=str(tmp_path))
        files = NASFileSystemSession(config).get_new_files()
        assert files == []


class TestNASConnector:
    @pytest.mark.asyncio
    async def test_connect_creates_session(self, tmp_path):
        connector = NASConnector({"nas_dir_path": str(tmp_path)})
        session = await connector.connect()
        assert isinstance(session, NASFileSystemSession)

    @pytest.mark.asyncio
    async def test_connect_reuses_session(self, tmp_path):
        connector = NASConnector({"nas_dir_path": str(tmp_path)})
        s1 = await connector.connect()
        s2 = await connector.connect()
        assert s1 is s2

    @pytest.mark.asyncio
    async def test_close_releases_session(self, tmp_path):
        connector = NASConnector({"nas_dir_path": str(tmp_path)})
        await connector.connect()
        assert connector._session is not None
        await connector.close()
        assert connector._session is None
