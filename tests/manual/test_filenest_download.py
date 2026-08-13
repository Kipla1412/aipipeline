"""Manual FileNest read/download test — real FileNest credentials required.

Loads configuration from environment variables:
    FILENEST_API_KEY
    FILENEST_PROJECT_ID
    FILENEST_API_URL

Flow:
    1. Create FileNestConnector
    2. Create FileNestDownloader
    3. list_files() — print id/filename/status/metadata
    4. download_to_temp(file_id) — pick a known file ID

No uploads. No PostgreSQL. No Airflow.

Usage:
    python3 tests/manual/test_filenest_download.py
    python3 tests/manual/test_filenest_download.py <file_id>   # download specific file
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.components.connectors.filenest import FileNestConnector
from src.components.extractors.filenest import FileNestDownloader


def main() -> None:
    api_key = os.environ.get("FILENEST_API_KEY")
    project_id = os.environ.get("FILENEST_PROJECT_ID")
    base_url = os.environ.get("FILENEST_API_URL")

    if not (api_key and project_id and base_url):
        print("Missing environment variables. Set:")
        print("  FILENEST_API_KEY")
        print("  FILENEST_PROJECT_ID")
        print("  FILENEST_API_URL")
        sys.exit(1)

    print("=" * 60)
    print("  FileNest — read/download manual test")
    print("=" * 60)

    connector = FileNestConnector({
        "api_key": api_key,
        "project_id": project_id,
        "base_url": base_url,
    })
    downloader = FileNestDownloader(
        connector, {"download_dir": "storage/temp"}
    )

    # 1. List files
    print("\n--- list_files() ---")
    files = downloader.list_files()
    print(f"  Total files: {len(files)}\n")
    for f in files:
        print(f"  id:       {f.id}")
        print(f"  filename: {f.filename}")
        print(f"  status:   {f.status}")
        print(f"  metadata: {f.metadata}")
        print()

    # 2. Download a specific file
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    file_id = args[0] if args else None

    if file_id:
        print(f"--- download_to_temp({file_id}) ---")
        path = downloader.download_to_temp(file_id)
        print(f"\n  Downloaded to: {path}")
    else:
        print("Pass a file_id argument to download:")
        print("  python3 tests/manual/test_filenest_download.py <file_id>")

    downloader.close()


if __name__ == "__main__":
    main()
