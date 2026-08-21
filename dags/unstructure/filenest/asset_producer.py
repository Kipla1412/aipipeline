"""
FileNest Asset Producer DAG
===========================

This DAG is a pure **asset trigger** for the medical-file pipeline.

Purpose
-------
The producer does NOT download files. It only:

1. Connects to the fhir-staging service (Airflow connection ``fhir-staging``).
2. Fetches staging records with ``status=pending``.
3. Logs each pending record and its ``file_id``.
4. Emits the ``medical_files_asset`` Airflow Asset.

The consumer DAG (``filenest_asset_consumer``) is scheduled on that Asset and
is the ONLY component that downloads the FileNest file and runs
extract → classify → transform.

Architecture
------------
    FHIR Staging (pending records)
         |
         v
    FhirStagingClient
         |
         v
    medical_files_asset (emit)
         |
         v
    filenest_asset_consumer (download + process)

Asset
-----
The ``medical_files_asset`` represents "there is work available" — it does not
contain the file itself. The consumer pulls the pending records directly from
fhir-staging when triggered.
"""

import logging
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

from src.components.credentials.factory import CredentialFactory
from src.components.fhir_staging.client import FhirStagingClient
from src.components.utils.reader import load_yml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONFIG_PATH = Path(__file__).parent / "config" / "config.yml"
cfg = load_yml(CONFIG_PATH)

# ---------------------------------------------------------------------------
# Airflow Asset (shared with the consumer)
# ---------------------------------------------------------------------------
medical_files_asset = Asset(
    name=cfg.get("asset", {}).get("name", "medical_files_asset"),
    uri=cfg.get("asset", {}).get("uri", "file:///medical/files/available"),
    group=cfg.get("asset", {}).get("group", "filenest"),
)


def _fhir_staging_base_url() -> str:
    """Build http://host:port from the 'fhir-staging' Airflow connection."""
    conn_id = cfg.get("credentials", {}).get("fhir_staging_conn_id", "fhir-staging")
    creds = CredentialFactory.get_provider(
        mode="airflow",
        conn_id=conn_id,
    ).get_credentials()

    host = creds.get("host") or "localhost"
    port = creds.get("port") or 8002
    return f"http://{host}:{port}"


def check_and_emit(**kwargs) -> dict:
    """
    Purpose:
        Pure asset trigger: fetch pending fhir-staging records, log their
        file_ids, and emit the medical_files_asset via task outlets.

        Does NOT download files, does NOT create a FileNest connector or
        downloader, does NOT create temporary files.

    Returns:
        dict: Summary with pending count and their file_ids.
    """
    base_url = _fhir_staging_base_url()
    logger.info("FHIR-Staging endpoint: %s", base_url)

    with FhirStagingClient(base_url=base_url) as staging_client:
        records = staging_client.list_pending_records()
        logger.info("Found %d pending staging record(s)", len(records))

        file_ids = []
        for record in records:
            staging_record_id = record.get("staging_record_id") or record.get("id")
            file_id = record.get("file_id")
            filename = record.get("attachment_title") or file_id
            logger.info(
                "Pending record: staging_record_id=%s file_id=%s filename=%s",
                staging_record_id,
                file_id,
                filename,
            )
            if file_id:
                file_ids.append(file_id)

        # The task declares outlets=[medical_files_asset]; Airflow emits the
        # Asset event when this task completes successfully, which schedules
        # the consumer DAG.
        logger.info("Emitting medical_files_asset for %d pending file(s)", len(file_ids))
        return {"found": len(records), "file_ids": file_ids}


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
    schedule="*/1 * * * *",
    catchup=False,
    description=(
        "Asset trigger: check fhir-staging for pending records and "
        "emit medical_files_asset (no downloads)"
    ),
    tags=["filenest", "staging", "asset", "producer"],
) as dag:

    check_task = PythonOperator(
        task_id="check_pending_records",
        python_callable=check_and_emit,
        outlets=[medical_files_asset],
    )
