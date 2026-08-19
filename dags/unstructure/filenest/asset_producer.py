"""
FileNest Asset Producer DAG
===========================

This DAG implements the ingestion stage of the medical-file pipeline.

Purpose
-------
The DAG polls the FHIR Staging service for records that are waiting to be
processed. For each pending record, it:

1. Retrieves the pending staging records.
2. Loads FileNest credentials through the credential factory.
3. Creates a FileNest connector.
4. Downloads the referenced medical file to a temporary directory.
5. Marks the staging record as ``processing`` before downloading.
6. Marks the record as ``failed`` if the download fails.
7. Emits the ``medical_files_asset`` when the task completes successfully.

The emitted Airflow Asset can be consumed by downstream DAGs or tasks that
depend on new medical files becoming available.

Architecture
------------
The DAG follows the project's factory-based architecture:

    FHIR Staging
         |
         v
    FhirStagingClient
         |
         v
    CredentialFactory
         |
         v
    ConnectorFactory
         |
         v
    FileNest Connector
         |
         v
    ExtractorFactory
         |
         v
    FileNest Extractor
         |
         v
    Local temporary file
         |
         v
    Airflow Asset

Configuration
-------------
Runtime configuration is loaded from::

    dags/config/config.yml

The following configuration sections are used:

``asset``
    Defines the Airflow Asset name, URI, and group.

``credentials``
    Defines the Airflow connection ID used to retrieve FileNest credentials.

``filenest``
    Defines the directory used for temporary FileNest downloads.

``pipeline``
    Defines DAG retry settings, retry delay, and schedule.

Environment Variable Fallbacks
------------------------------
FileNest credentials can fall back to environment variables when they are
not available through the configured Airflow connection:

    FILENEST_API_KEY
    FILENEST_PROJECT_ID
    FILENEST_API_URL

Failure Handling
----------------
Individual staging records are processed independently.

If a record is missing ``file_id``:
    The record is marked as ``failed`` and processing continues with the next
    record.

If FileNest download fails:
    The exception is logged, the record is marked as ``failed``, and processing
    continues with the next record.

If the entire task succeeds, the Airflow Asset is emitted.

The FileNest extractor is always closed using a ``finally`` block to prevent
resource leaks.

Idempotency / Record Claiming
-----------------------------
A pending staging record is changed to ``processing`` before its FileNest
download begins. This prevents the record from remaining in the pending state
while it is actively being handled.

The FHIR Staging service is therefore responsible for maintaining the record
state used by this ingestion process.

Asset
-----
The ``medical_files_asset`` represents the availability of newly downloaded
medical files. Downstream consumers can use this Asset as a dependency rather
than relying only on a time-based schedule.
"""

import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Project Paths
# ---------------------------------------------------------------------------
_AI_PLATFORM = Path(__file__).resolve().parents[3]

if str(_AI_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_AI_PLATFORM))

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import Asset

from src.components.connectors.factory import ConnectorFactory
from src.components.credentials.factory import CredentialFactory
from src.components.extractors.factory import ExtractorFactory
from src.components.fhir_staging.client import FhirStagingClient
from src.components.utils.reader import load_yml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONFIG_PATH = Path(__file__).parent / "config" / "config.yml"
cfg = load_yml(CONFIG_PATH)

# ---------------------------------------------------------------------------
# Airflow Asset
# ---------------------------------------------------------------------------
medical_files_asset = Asset(
    name=cfg.get("asset", {}).get("name", "medical_files_asset"),
    uri=cfg.get("asset", {}).get("uri", "file:///medical/files/available"),
    group=cfg.get("asset", {}).get("group", "filenest"),
)


def run_filenest_ingestion(**kwargs) -> dict:
    """Download pending medical files from FileNest.

    The function retrieves pending records from the FHIR Staging service,
    claims each record by changing its status to ``processing``, downloads
    the corresponding FileNest file, and updates the record status when
    processing fails.

    Returns:
        dict: Summary containing found and downloaded record counts.
    """
    logger.info("Checking FHIR Staging for pending records")

    # 1. Retrieve pending staging records
    with FhirStagingClient() as staging_client:
        records = staging_client.list_pending_records()
        logger.info("Found %d pending staging record(s)", len(records))

        if not records:
            return {"found": 0, "downloaded": 0}

        # 2. Resolve FileNest credentials
        filenest_conn_id = cfg.get("credentials", {}).get(
            "filenest_conn_id", "filenest_conn"
        )

        filenest_creds = CredentialFactory.get_provider(
            mode="airflow",
            conn_id=filenest_conn_id,
        ).get_credentials()

        logger.info(
            "FileNest credentials loaded: project_id=%s base_url=%s api_key_present=%s",
            filenest_creds.get("project_id"),
            filenest_creds.get("base_url") or filenest_creds.get("host"),
            bool(filenest_creds.get("api_key")),
        )

        api_key = filenest_creds.get("api_key") or os.environ.get("FILENEST_API_KEY")
        project_id = filenest_creds.get("project_id") or os.environ.get("FILENEST_PROJECT_ID")
        base_url = (
            filenest_creds.get("base_url")
            or filenest_creds.get("host")
            or os.environ.get("FILENEST_API_URL")
        )

        if base_url and not base_url.startswith(("http://", "https://")):
            base_url = f"https://{base_url}"

        if not api_key or not project_id or not base_url:
            raise RuntimeError("FileNest credentials are missing")

        # 3. Create FileNest connector and extractor
        filenest = ConnectorFactory.get_connector(
            "filenest",
            {
                "api_key": api_key,
                "project_id": project_id,
                "base_url": base_url,
            },
        )

        download_dir = cfg.get("filenest", {}).get("download_dir", "storage/temp")
        if not os.path.isabs(download_dir):
            download_dir = os.path.join(_AI_PLATFORM, download_dir)

        downloader = ExtractorFactory.get_extractor(
            "filenest",
            connection=filenest,
            config={"download_dir": download_dir},
        )

        downloaded_count = 0

        try:
            # 4. Process each pending staging record
            for record in records:
                staging_record_id = record.get("staging_record_id") or record.get("id")
                file_id = record.get("file_id")
                filename = record.get("attachment_title") or f"{file_id}.bin"

                if not staging_record_id:
                    logger.error("Staging record has no ID: %s", record)
                    continue

                if not file_id:
                    logger.error("Staging record %s has no file_id", staging_record_id)
                    staging_client.update_status(
                        staging_record_id,
                        "failed",
                        "Missing FileNest file_id",
                    )
                    continue

                logger.info(
                    "Processing staging record=%s file_id=%s filename=%s",
                    staging_record_id,
                    file_id,
                    filename,
                )

                # 5. Claim the record
                staging_client.update_status(staging_record_id, "processing")

                try:
                    # 6. Download FileNest file
                    local_path = downloader.download_to_temp(
                        file_id,
                        filename=filename,
                    )
                    logger.info("Downloaded FileNest file → %s", local_path)
                    downloaded_count += 1

                except Exception as exc:
                    logger.exception("FileNest download failed for %s", file_id)

                    # 7. Mark record as failed
                    staging_client.update_status(
                        staging_record_id,
                        "failed",
                        str(exc),
                    )
                    continue

        finally:
            downloader.close()

        logger.info("Downloaded %d file(s)", downloaded_count)
        return {
            "found": len(records),
            "downloaded": downloaded_count,
        }


# ---------------------------------------------------------------------------
# DAG Definition
# ---------------------------------------------------------------------------
with DAG(
    "filenest_asset_producer",
    default_args={
        "owner": "alpha_team",
        "retries": cfg.get("pipeline", {}).get("retries", 1),
        "retry_delay": timedelta(
            minutes=cfg.get("pipeline", {}).get("retry_delay_minutes", 5)
        ),
    },
    start_date=datetime(2026, 1, 1),
    schedule=cfg.get("pipeline", {}).get("schedule", "@daily"),
    catchup=False,
    description=(
        "Read pending FHIR staging records, "
        "download FileNest files, mark processing"
    ),
    tags=["filenest", "staging", "asset", "producer"],
) as dag:

    ingest_task = PythonOperator(
        task_id="filenest_ingestion",
        python_callable=run_filenest_ingestion,
        outlets=[medical_files_asset],
    )