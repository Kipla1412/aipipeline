"""
Module: FileNest Asset Producer DAG (Airflow 3 Orchestration)
Purpose:
    Runs the full ingestion chain inside Airflow:
        FileNestConnector → FileNestDownloader → storage/temp/
        → FileNestRepository → PostgreSQL (download_status=downloaded)
        → emit Asset event

    When at least one file is downloaded successfully, the 'medical_files_asset'
    Asset event is emitted, making the consumer DAG eligible to run.

Asset:
    medical_files_asset  (uri: file:///medical/files/available)

Schedule: @daily
"""

import sys
import os
from pathlib import Path
_AI_PLATFORM = Path(__file__).resolve().parent.parent.parent.parent
if str(_AI_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_AI_PLATFORM))

import warnings
import logging

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", module="skops")
logging.getLogger("skops").setLevel(logging.ERROR)

from datetime import datetime, timedelta
from airflow import DAG
from airflow.sdk import Asset
from airflow.providers.standard.operators.python import PythonOperator

from dotenv import load_dotenv

from src.components.credentials.factory import CredentialFactory
from src.components.connectors.factory import ConnectorFactory
from src.components.extractors.factory import ExtractorFactory
from src.components.repository.filenestrepository import FileNestRepository
from src.components.repository.models import FileNestFileRecord, DownloadStatus
from src.components.utils.config import PipelineConfig
from src.components.utils.reader import load_yml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config" / "config.yml"

# Load .env (works in Airflow worker + local dev)
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent.parent / ".env")


def load_config() -> dict:
    return load_yml(CONFIG_PATH)


cfg = load_config()

# One logical Asset representing availability of downloaded medical files.
medical_files_asset = Asset(
    name=cfg.get("asset", {}).get("name", "medical_files_asset"),
    uri=cfg.get("asset", {}).get("uri", "file:///medical/files/available"),
    group=cfg.get("asset", {}).get("group", "filenest"),
    extra={"description": "Emitted when FileNest files have been downloaded and stored in PostgreSQL"},
)


def run_filenest_to_postgres(**kwargs) -> dict:
    """Full chain: list → download → save to Postgres → mark downloaded.

    Returns dict with counts so the log shows what happened.
    """
    # Credentials from Airflow Connections (Admin → Connections)
    #   filenest_conn:  extras = {api_key, project_id, base_url}
    #   postgres_conn:  host, login, password, schema
    filenest_conn_id = cfg.get("credentials", {}).get("filenest_conn_id", "filenest_conn")
    postgres_conn_id = cfg.get("credentials", {}).get("postgres_conn_id", "postgres_conn")

    filenest_creds = CredentialFactory.get_provider(mode="airflow", conn_id=filenest_conn_id).get_credentials()
    api_key = filenest_creds.get("api_key") or os.environ.get("FILENEST_API_KEY")
    project_id = filenest_creds.get("project_id") or os.environ.get("FILENEST_PROJECT_ID")
    base_url = filenest_creds.get("base_url") or filenest_creds.get("host") or os.environ.get("FILENEST_API_URL")
    if base_url and not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"
    if not (api_key and project_id and base_url):
        raise RuntimeError(
            f"FileNest credentials missing — set extras on Airflow connection '{filenest_conn_id}' "
            "(api_key, project_id, base_url) or FILENEST_* env vars"
        )

    # 1. FileNest connector + downloader (via factories)
    logger.info("Connecting to FileNest (project=%s)", project_id)
    filenest = ConnectorFactory.get_connector("filenest", {
        "api_key": api_key,
        "project_id": project_id,
        "base_url": base_url,
    })
    download_dir = cfg.get("filenest", {}).get("download_dir", "storage/temp")
    download_dir = os.path.join(_AI_PLATFORM, download_dir) if not os.path.isabs(download_dir) else download_dir
    downloader = ExtractorFactory.get_extractor(
        "filenest", connection=filenest, config={"download_dir": download_dir}
    )

    # 2. List files
    files = downloader.list_files()
    logger.info("FileNest has %d file(s)", len(files))
    if not files:
        return {"downloaded": 0, "total": 0}

    # 3. PostgreSQL repository — credentials from Airflow connection
    postgres_creds = CredentialFactory.get_provider(mode="airflow", conn_id=postgres_conn_id).get_credentials()
    rdbms_config = {
        "type": "postgresql",
        "host": postgres_creds.get("host", "localhost"),
        "port": int(postgres_creds.get("port") or 5432),
        "database": postgres_creds.get("schema") or postgres_creds.get("database", "fhir-staging"),
        "login": postgres_creds.get("login"),
        "password": postgres_creds.get("password"),
    }
    connector = ConnectorFactory.get_connector("rdbms", rdbms_config)
    repo = FileNestRepository(connector)

    # Known file ids already downloaded/processed — skip them (dedup)
    known = {r.filenest_file_id for r in repo.list_all()}
    downloaded_count = 0
    try:
        for f in files:
            if f.id in known:
                logger.info("Skipping %s (%s) — already in PostgreSQL", f.filename, f.id[:8])
                continue
            file_meta = downloader.get_file(f.id)
            logger.info("Processing: %s (%s)", file_meta.filename, file_meta.id[:8])

            # Download to temp — prefix with file_id to avoid duplicate filename collisions
            unique_name = f"{file_meta.id[:8]}_{file_meta.filename}"
            local_path = downloader.download_to_temp(file_meta.id, filename=unique_name)
            logger.info("  Downloaded → %s (%d bytes)", local_path, local_path.stat().st_size)

            # Save to Postgres
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
            repo.save(record)
            repo.update_download_status(file_meta.id, DownloadStatus.DOWNLOADED)
            downloaded_count += 1
            logger.info("  Saved + marked downloaded ✓")
    finally:
        repo.close()
        downloader.close()

    logger.info("Downloaded %d file(s) — Asset will be emitted", downloaded_count)
    return {"downloaded": downloaded_count, "total": len(files)}


with DAG(
    "filenest_asset_producer",
    default_args={"owner": "alpha_team",
                  "retries": cfg.get("pipeline", {}).get("retries", 1),
                  "retry_delay": timedelta(minutes=cfg.get("pipeline", {}).get("retry_delay_minutes", 5))},
    start_date=datetime(2026, 1, 1),
    schedule=cfg.get("pipeline", {}).get("schedule", "@daily"),
    catchup=False,
    description="Download FileNest files → PostgreSQL → emit medical_files_asset",
    tags=["filenest", "asset", "producer"],
) as dag:

    ingest_task = PythonOperator(
        task_id="filenest_to_postgres_task",
        python_callable=run_filenest_to_postgres,
        outlets=[medical_files_asset],
    )
