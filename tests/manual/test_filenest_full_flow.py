"""Full FileNest end-to-end integration test — connector → list → URL → download → Postgres.

Tests the complete flow:
  1. FileNestConnector — connect to FileNest cloud
  2. FileNestDownloader.list_files() — list real files
  3. FileNestDownloader.get_file() — get metadata for one file
  4. FileNestDownloader.get_download_url() — generate signed URL
  5. FileNestDownloader.download_to_temp() — download to storage/temp/
  6. FileNestRepository.save() — persist metadata to PostgreSQL
  7. FileNestRepository.update_download_status() — mark as downloaded
  8. Verify — read back from PostgreSQL + check file exists on disk

Real credentials required (from .env):
  FILENEST_API_KEY, FILENEST_PROJECT_ID, FILENEST_API_URL
  POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB

Usage:
  python3 tests/manual/test_filenest_full_flow.py
  python3 tests/manual/test_filenest_full_flow.py <file_id>   # specific file
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

from src.components.connectors.filenest import FileNestConnector
from src.components.connectors.rdbms import RDBMSConnector
from src.components.extractors.filenest import FileNestDownloader
from src.components.repository.filenestrepository import FileNestRepository
from src.components.repository.models import FileNestFileRecord, DownloadStatus
from src.components.utils.config import PipelineConfig


def separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def main() -> None:
    api_key = os.environ.get("FILENEST_API_KEY")
    project_id = os.environ.get("FILENEST_PROJECT_ID")
    base_url = os.environ.get("FILENEST_API_URL")

    if not (api_key and project_id and base_url):
        print("Missing FileNest env vars. Set FILENEST_API_KEY/PROJECT_ID/API_URL in .env")
        sys.exit(1)

    # 1. FileNest Connector
    separator("STEP 1 — FileNestConnector")
    filenest = FileNestConnector({
        "api_key": api_key,
        "project_id": project_id,
        "base_url": base_url,
    })
    client = filenest()
    print(f"  Connected: project={project_id}")
    print(f"  Client type: {type(client).__name__}")

    # 2. Downloader + list files
    separator("STEP 2 — list_files()")
    downloader = FileNestDownloader(filenest, {"download_dir": "storage/temp"})
    files = downloader.list_files()
    print(f"  Total files: {len(files)}")
    for f in files[:5]:
        print(f"    {f.id}  {f.filename}  ({f.status})")
    if not files:
        print("  No files found — nothing to test.")
        return

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    file_id = args[0] if args else files[0].id
    target = next((f for f in files if f.id == file_id), files[0])

    # 3. Get file metadata
    separator("STEP 3 — get_file()")
    file_meta = downloader.get_file(target.id)
    print(f"  id:         {file_meta.id}")
    print(f"  filename:   {file_meta.filename}")
    print(f"  content:    {getattr(file_meta, 'content_type', '?')}")
    print(f"  size:       {getattr(file_meta, 'size_bytes', '?')} bytes")
    print(f"  metadata:   {getattr(file_meta, 'metadata', {})}")

    # 4. Get download URL
    separator("STEP 4 — get_download_url()")
    url = downloader.get_download_url(file_meta.id, ttl=3600)
    print(f"  Signed URL (ttl=3600s):")
    print(f"    {url[:100]}...")

    # 5. Download to temp
    separator("STEP 5 — download_to_temp()")
    local_path = downloader.download_to_temp(file_meta.id)
    print(f"  Downloaded → {local_path}")
    print(f"  File exists: {local_path.exists()}")
    print(f"  Size on disk: {local_path.stat().st_size} bytes")

    # 6. Persist metadata to PostgreSQL
    separator("STEP 6 — FileNestRepository.save()")
    rdbms_config = PipelineConfig().get_postgres_config()
    connector = RDBMSConnector(rdbms_config)
    repo = FileNestRepository(connector)

    record = FileNestFileRecord(
        filenest_file_id=file_meta.id,
        filename=file_meta.filename,
        filepath=str(local_path),
        content_type=getattr(file_meta, "content_type", None),
        size_bytes=getattr(file_meta, "size_bytes", None),
        filenest_status=getattr(file_meta, "status", None),
        metadata=getattr(file_meta, "metadata", None) or {},
        download_status=DownloadStatus.DOWNLOADING,
    )
    saved = repo.save(record)
    print(f"  Saved id={saved.id} filenest_file_id={saved.filenest_file_id}")
    print(f"  download_status={saved.download_status}")

    # 7. Mark as downloaded
    separator("STEP 7 — update_download_status(downloaded)")
    repo.update_download_status(file_meta.id, DownloadStatus.DOWNLOADED)
    updated = repo.get_by_file_id(file_meta.id)
    print(f"  download_status: {updated.download_status}")
    print(f"  downloaded_at:   {updated.downloaded_at}")

    # 8. Verify read-back
    separator("STEP 8 — Verify read-back")
    print(json.dumps(updated.model_dump(), indent=2, default=str))
    print(f"\n  exists(): {repo.exists(file_meta.id)}")
    print(f"  File on disk: {local_path.exists()}")

    repo.close()
    downloader.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
