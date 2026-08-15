"""Manual FileNest → PostgreSQL repository integration test — real credentials required.

Loads configuration from environment variables:
    FILENEST_API_KEY
    FILENEST_PROJECT_ID
    FILENEST_API_URL

Flow:
    1. Create RDBMSConnector (PostgreSQL) via LocalCredentialProvider
    2. Create FileNestRepository
    3. Create FileNestConnector + FileNestDownloader
    4. list_files() — take the first real FileNest file
    5. repo.save(record) — persist its metadata
    6. repo.get_by_file_id() — read it back
    7. Print the stored record (raw JSON)

No download is performed. No Airflow. No uploads.

Usage:
    python3 tests/manual/test_filenest_repository.py
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
from src.components.utils.config import PipelineConfig
from src.components.extractors.filenest import FileNestDownloader
from src.components.repository.filenestrepository import FileNestRepository
from src.components.repository.models import FileNestFileRecord


def main() -> None:
    api_key = os.environ.get("FILENEST_API_KEY")
    project_id = os.environ.get("FILENEST_PROJECT_ID")
    base_url = os.environ.get("FILENEST_API_URL")

    if not (api_key and project_id and base_url):
        print("Missing FileNest environment variables. Set:")
        print("  FILENEST_API_KEY")
        print("  FILENEST_PROJECT_ID")
        print("  FILENEST_API_URL")
        sys.exit(1)

    print("=" * 60)
    print("  FileNest → PostgreSQL repository manual test")
    print("=" * 60)

    # 1. PostgreSQL connector + repository (credentials via PipelineConfig)
    print("\n--- Connecting to PostgreSQL ---")
    rdbms_config = PipelineConfig().get_postgres_config()

    connector = RDBMSConnector(rdbms_config)
    repo = FileNestRepository(connector)

    # 2. FileNest connector + downloader (list only, no download)
    print("\n--- Connecting to FileNest ---")
    filenest = FileNestConnector({
        "api_key": api_key,
        "project_id": project_id,
        "base_url": base_url,
    })
    downloader = FileNestDownloader(filenest, {"download_dir": "storage/temp"})

    # 3. Get one real FileNest file
    files = downloader.list_files()
    if not files:
        print("No files found in FileNest. Nothing to persist.")
        sys.exit(0)
    f = files[0]
    print(f"\n  Picked FileNest file:")
    print(f"    id:       {f.id}")
    print(f"    filename: {f.filename}")
    print(f"    status:   {f.status}")

    # 4. Save its metadata into PostgreSQL
    print("\n--- repo.save() ---")
    record = FileNestFileRecord(
        filenest_file_id=f.id,
        filename=f.filename,
        content_type=getattr(f, "content_type", None),
        size_bytes=getattr(f, "size_bytes", None),
        filenest_status=getattr(f, "status", None),
        metadata=getattr(f, "metadata", None) or {},
    )
    saved = repo.save(record)
    print(f"  Saved id={saved.id} filenest_file_id={saved.filenest_file_id}")

    # 5. Query it back
    print("\n--- repo.get_by_file_id() ---")
    fetched = repo.get_by_file_id(f.id)
    if fetched is None:
        print("  ERROR: record not found!")
        sys.exit(1)
    print("  Found record:")
    print(json.dumps(fetched.model_dump(), indent=2, default=str))

    print("\n--- exists() / pending ---")
    print(f"  exists({f.id})            = {repo.exists(f.id)}")
    print(f"  exists(random-uuid)       = {repo.exists('00000000-0000-0000-0000-000000000000')}")
    print(f"  pending files             = {len(repo.get_pending_files())}")

    repo.close()
    downloader.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
