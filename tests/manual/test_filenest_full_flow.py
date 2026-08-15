"""Full FileNest end-to-end integration test — connector → list → URL → download → Postgres.

Processes files one by one:
  --all                : loop over ALL files (download → save → mark downloaded → next)
  <file_id>            : single specific file
  (no arg)             : first file in the list

Real credentials required (from .env):
  FILENEST_API_KEY, FILENEST_PROJECT_ID, FILENEST_API_URL
  POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB

Usage:
  python3 tests/manual/test_filenest_full_flow.py --all
  python3 tests/manual/test_filenest_full_flow.py <file_id>
  python3 tests/manual/test_filenest_full_flow.py
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


def process_one(downloader, repo, file_meta) -> None:
    """Download one file, save metadata to Postgres, mark downloaded."""
    print(f"\n  ▶ Processing: {file_meta.filename} ({file_meta.id[:8]}...)")

    url = downloader.get_download_url(file_meta.id, ttl=3600)
    print(f"    URL: {url[:80]}...")

    local_path = downloader.download_to_temp(file_meta.id)
    print(f"    Downloaded → {local_path} ({local_path.stat().st_size} bytes)")

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
    print(f"    Saved to Postgres: id={saved.id}")

    repo.update_download_status(file_meta.id, DownloadStatus.DOWNLOADED)
    print(f"    Status: downloaded ✓")


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

    # 2. List files
    separator("STEP 2 — list_files()")
    downloader = FileNestDownloader(filenest, {"download_dir": "storage/temp"})
    files = downloader.list_files()
    print(f"  Total files: {len(files)}")
    for f in files:
        print(f"    {f.id}  {f.filename}  ({f.status})")
    if not files:
        print("  No files found — nothing to test.")
        return

    # 3. Postgres repo (single connection reused for all files)
    separator("SETUP — PostgreSQL repository")
    rdbms_config = PipelineConfig().get_postgres_config()
    connector = RDBMSConnector(rdbms_config)
    repo = FileNestRepository(connector)
    print("  Connected to PostgreSQL")

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    process_all = "--all" in sys.argv

    if process_all:
        separator(f"PROCESSING ALL {len(files)} FILES (one by one)")
        for f in files:
            file_meta = downloader.get_file(f.id)
            process_one(downloader, repo, file_meta)
    elif args:
        file_meta = downloader.get_file(args[0])
        separator(f"PROCESSING SINGLE FILE — {file_meta.filename}")
        process_one(downloader, repo, file_meta)
    else:
        file_meta = downloader.get_file(files[0].id)
        separator(f"PROCESSING FIRST FILE — {file_meta.filename}")
        process_one(downloader, repo, file_meta)

    # 4. Verify
    separator("VERIFY — Postgres read-back")
    all_records = repo.list_all()
    downloaded = [r for r in all_records if r.download_status == "downloaded"]
    print(f"  Records in Postgres: {len(all_records)}")
    print(f"  Downloaded: {len(downloaded)}")
    for r in downloaded[-5:]:
        print(f"    {r.filenest_file_id[:8]}... {r.filename} [{r.download_status}]")

    repo.close()
    downloader.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
