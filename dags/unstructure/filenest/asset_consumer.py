"""
Module: FileNest Asset Consumer DAG

Purpose:
    Monitors and consumes Airflow Assets triggered by upstream file ingestions,
    downloads pending files from FileNest using temporary disk storage, performs
    multi-stage extraction, classification, and transformation into a Clinical
    Domain Model JSON, and updates the existing fhir-staging service records.

Pipeline Architecture:
    1. Asset Trigger: Receives `medical_files_asset` event.
    2. Staging Fetch: Polls `fhir-staging` API for records with status='pending'.
    3. Status Update: Marks record as 'processing'.
    4. Temporary Download: Streams file from FileNest into a managed temp directory.
    5. Document Processing:
        - Extract: OCR / DICOM metadata / Image analysis via AI Extractor Factory.
        - Classify: LLM-based document categorization (e.g., GPT-4o-mini).
        - Transform: Converts extracted markdown/metadata to Clinical Domain JSON.
        - Persistence: Writes JSON payload to configured storage path.
    6. Staging Update: PATCHes observations & marks status as 'completed' (or 'failed').
    7. Storage Cleanup: Automatically purges temporary files regardless of task outcome.

Dependencies:
    - Apache Airflow >= 3.0
    - src.components.connectors.factory.ConnectorFactory
    - src.components.extractors.factory.ExtractorFactory
    - src.components.fhir_staging.client.FhirStagingClient
    - src.components.transformers.factory.TransformerFactory
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import warnings

# ---------------------------------------------------------------------------
# Project Path Configuration
# ---------------------------------------------------------------------------

_AI_PLATFORM: Path = Path(__file__).resolve().parent.parent.parent.parent

if str(_AI_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_AI_PLATFORM))


# ---------------------------------------------------------------------------
# Logging & Warning Configurations
# ---------------------------------------------------------------------------

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", module="skops")

logging.getLogger("skops").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Airflow SDK Imports
# ---------------------------------------------------------------------------

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import Asset


# ---------------------------------------------------------------------------
# Application Component Imports
# ---------------------------------------------------------------------------

from src.components.connectors.factory import ConnectorFactory
from src.components.extractors.factory import ExtractorFactory
from src.components.fhir_staging.client import FhirStagingClient
from src.components.transformers.factory import TransformerFactory
from src.components.credentials.factory import CredentialFactory
from src.components.utils.config import PipelineConfig
from src.components.utils.reader import load_yml


# ---------------------------------------------------------------------------
# Configuration Setup
# ---------------------------------------------------------------------------

CONFIG_PATH: Path = Path(__file__).parent / "config" / "config.yml"


def load_config() -> dict[str, Any]:
    """
    Loads and parses YAML configuration settings for the DAG.

    Returns:
        dict[str, Any]: Parsed configuration dictionary.
    """
    return load_yml(CONFIG_PATH)


def _abs_path(value: str | None, default: Path) -> Path:
    """
    Purpose:
        Resolves a possibly-relative path from config.yml against the project
        root (_AI_PLATFORM) so Airflow workers never write to the wrong CWD.

    Args:
        value: Raw path from config.yml (absolute, 'aiplatform/...', or relative).
        default: Fallback path when value is empty.

    Returns:
        Path: Absolute path.
    """
    if not value:
        return default
    p = Path(value)
    if p.is_absolute():
        return p
    # Config uses the repo-name prefix ("aiplatform/storage/...") — strip it,
    # since _AI_PLATFORM already IS the aiplatform directory.
    if value.startswith("aiplatform/"):
        p = Path(value[len("aiplatform/"):])
    return _AI_PLATFORM / p


cfg: dict[str, Any] = load_config()


# ---------------------------------------------------------------------------
# Asset Definition
# ---------------------------------------------------------------------------

medical_files_asset = Asset(
    name=cfg.get("asset", {}).get("name", "medical_files_asset"),
    uri=cfg.get("asset", {}).get("uri", "file:///medical/files/available"),
    group=cfg.get("asset", {}).get("group", "filenest"),
)


# ===========================================================================
# FILE PROCESSING ENGINE
# ===========================================================================


def process_one_file(file_record: dict[str, Any]) -> dict[str, Any]:
    """
    Executes the extraction, classification, and transformation pipeline on a single file.

    Args:
        file_record (dict[str, Any]): Dictionary containing metadata about the target file.
            Required keys:
                - 'filepath' (str | Path): Physical path to the local temporary file.
                - 'filename' (str): Original filename or alias.
                - 'filenest_file_id' (str): Unique FileNest asset identifier.

    Returns:
        dict[str, Any]: Execution status dictionary containing:
            - 'status' (str): 'processed' or 'failed'.
            - 'filename' (str): Name of the file processed.
            - 'observations' (list): Extracted clinical observations if successful.
            - 'reason' (str, optional): Error details if status is 'failed'.
            - 'output' (str, optional): Destination file path of the transformed JSON.

    Notes:
        This function operates exclusively on local files and does not directly mutate
        remote HTTP staging records.
    """
    filepath = Path(file_record["filepath"])
    filename = file_record.get("filename", filepath.name)
    file_id = file_record.get("filenest_file_id", "")

    # -----------------------------------------------------------------------
    # 1. Physical File Validation
    # -----------------------------------------------------------------------
    if not filepath.exists():
        logger.warning("File does not exist on disk: %s", filepath)
        return {
            "filename": filename,
            "status": "failed",
            "reason": f"File missing on disk: {filepath}",
            "observations": [],
        }

    # -----------------------------------------------------------------------
    # 2. Media Type Detection
    # -----------------------------------------------------------------------
    suffix = filepath.suffix.lower()
    is_dicom = suffix in (".dcm", ".dicom")
    is_pdf = suffix == ".pdf"
    is_image = suffix in (".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp")

    if not (is_dicom or is_pdf or is_image):
        logger.warning("Unsupported file format encountered: %s", suffix)
        return {
            "filename": filename,
            "status": "failed",
            "reason": f"Unsupported file extension: {suffix}",
            "observations": [],
        }

    settings = PipelineConfig()

    # -----------------------------------------------------------------------
    # 3. Extraction Phase
    # -----------------------------------------------------------------------
    try:
        logger.info("Starting extraction for file: %s", filename)

        if is_dicom:
            extractor = ExtractorFactory.get_extractor(
                "dicom",
                config={
                    "output_image_dir": str(settings.EXTRACTED_IMAGE_DIR),
                    "extract_preview": True,
                },
            )
            extracted = extractor.extract(str(filepath))

        elif is_image:
            from src.components.extractors.schemas.extract_result import (
                ExtractResult,
            )

            image_analyzer = ExtractorFactory.get_extractor(
                "image",
                config={"api_key": settings.OPENAI_API_KEY},
            )
            description = asyncio.run(image_analyzer.extract([str(filepath)]))
            extracted = ExtractResult(
                markdown=description,
                images=[str(filepath)],
            )
            logger.info("Image multimodal analysis completed (%d chars)", len(description))

        else:
            extractor = ExtractorFactory.get_extractor(
                "pdf",
                config=settings.get_extractor_config(),
            )
            extracted = extractor.extract(str(filepath))

    except Exception as exc:
        logger.exception("Extraction stage failed for file: %s", filename)
        return {
            "filename": filename,
            "status": "failed",
            "reason": f"Extraction stage error: {exc}",
            "observations": [],
        }

    logger.info(
        "Extracted %s — %d markdown characters, %d embedded image(s)",
        filename,
        len(extracted.markdown),
        len(extracted.images),
    )

    # -----------------------------------------------------------------------
    # 4. Classification Phase
    # -----------------------------------------------------------------------
    try:
        classifier = TransformerFactory.get_transformer(
            "medical_classifier",
            config={
                "api_key": settings.OPENAI_API_KEY,
                "model": cfg.get("classification", {}).get("model", "gpt-4o-mini"),
            },
        )
        report_type = asyncio.run(classifier.classify(extracted.markdown))
        logger.info("Document classified [%s] → Type: %s", filename, report_type)

    except Exception as exc:
        logger.exception("Classification stage failed for file: %s", filename)
        return {
            "filename": filename,
            "status": "failed",
            "reason": f"Classification stage error: {exc}",
            "observations": [],
        }

    # -----------------------------------------------------------------------
    # 5. Transformation Phase
    # -----------------------------------------------------------------------
    try:
        transformer = TransformerFactory.get_transformer(
            "medical",
            config=settings.get_transformer_config(),
        )
        document = asyncio.run(
            transformer.transform(
                extracted.markdown,
                dicom_metadata=(extracted.dicom_metadata if is_dicom else None),
            )
        )
        document["report_type"] = report_type
        document["source_file"] = filename
        document["filenest_file_id"] = file_id

    except Exception as exc:
        logger.exception("Transformation stage failed for file: %s", filename)
        return {
            "filename": filename,
            "status": "failed",
            "reason": f"Transformation stage error: {exc}",
            "observations": [],
        }

    observations = document.get("observations", [])
    obs_count = len(observations)
    diagnosis_count = len(document.get("diagnoses", []))

    logger.info(
        "Transformed %s — Observations: %d, Diagnoses: %d",
        filename,
        obs_count,
        diagnosis_count,
    )

    # -----------------------------------------------------------------------
    # 6. JSON Schema Output Persistence
    # -----------------------------------------------------------------------
    try:
        out_dir = _abs_path(
            cfg.get("transformation", {}).get("output_dir"),
            _AI_PLATFORM / "storage" / "emr" / "transformed",
        )
        out_dir.mkdir(parents=True, exist_ok=True)

        file_id_short = file_id[:8] if file_id else "unknown"
        out_path = out_dir / f"{Path(filename).stem}_{file_id_short}.json"

        out_path.write_text(
            json.dumps(
                document,
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )
        logger.info("Persisted Clinical Domain JSON → %s", out_path)

    except Exception as exc:
        logger.exception("Failed to write output JSON for file: %s", filename)
        return {
            "filename": filename,
            "status": "failed",
            "reason": f"JSON persistence error: {exc}",
            "observations": observations,
        }

    return {
        "filename": filename,
        "status": "processed",
        "report_type": report_type,
        "observations": observations,
        "observations_count": obs_count,
        "diagnoses": diagnosis_count,
        "output": str(out_path),
    }

def medical_processing(**kwargs: Any) -> list[dict[str, Any]]:
    """
    Main Airflow PythonOperator task logic: pull pending fhir-staging records,
    download each referenced file from FileNest, run extract → classify →
    transform, persist the Clinical Domain Model JSON, and PATCH the same
    staging record to completed (or failed with error_message).

    The Asset is only the trigger — the work queue comes from the fhir-staging
    API (GET /api/v1/staging-records/?status=pending).
    """
    logger.info("Initiating medical file consumer process...")
    results: list[dict[str, Any]] = []

    # 1. Fetch FHIR-Staging Credentials (Airflow Connection: host + port)
    fhir_staging_conn_id = cfg.get("credentials", {}).get(
        "fhir_staging_conn_id", "fhir-staging"
    )
    fhir_staging_creds = CredentialFactory.get_provider(
        mode="airflow",
        conn_id=fhir_staging_conn_id,
    ).get_credentials()

    fhir_staging_host = fhir_staging_creds.get("host") or "localhost"
    fhir_staging_port = fhir_staging_creds.get("port") or 8002
    fhir_staging_base_url = f"http://{fhir_staging_host}:{fhir_staging_port}"
    logger.info("FHIR-Staging endpoint: %s", fhir_staging_base_url)

    # 2. Fetch FileNest Credentials (Airflow Connection: filenest_api_url)
    filenest_conn_id = cfg.get("credentials", {}).get(
        "filenest_conn_id", "filenest_conn_id"
    )
    filenest_creds = CredentialFactory.get_provider(
        mode="airflow",
        conn_id=filenest_conn_id,
    ).get_credentials()

    api_key = filenest_creds.get("api_key")
    project_id = filenest_creds.get("project_id")
    filenest_base_url = (
        filenest_creds.get("filenest_api_url")
        or filenest_creds.get("base_url")
        or filenest_creds.get("host")
    )
    if filenest_base_url and not filenest_base_url.startswith(("http://", "https://")):
        filenest_base_url = f"https://{filenest_base_url}"

    if not api_key or not project_id or not filenest_base_url:
        raise RuntimeError(
            f"FileNest credentials missing from Airflow connection '{filenest_conn_id}' "
            "(api_key, project_id, filenest_api_url)"
        )

    filenest = ConnectorFactory.get_connector(
        "filenest",
        {
            "api_key": api_key,
            "project_id": project_id,
            "base_url": filenest_base_url,
        },
    )

    download_dir = _abs_path(
        cfg.get("filenest", {}).get("download_dir"),
        _AI_PLATFORM / "storage" / "temp",
    )
    download_dir.mkdir(parents=True, exist_ok=True)

    downloader = ExtractorFactory.get_extractor(
        "filenest",
        connection=filenest,
        config={"download_dir": str(download_dir)},
    )

    try:
        with FhirStagingClient(base_url=fhir_staging_base_url) as staging_client:
            records = staging_client.list_pending_records()
            logger.info("Retrieved %d pending record(s) from fhir-staging", len(records))

            if not records:
                logger.info("No records requiring processing. Terminating execution loop.")
                return results

            for record in records:
                staging_record_id = record.get("staging_record_id") or record.get("id")
                file_id = record.get("file_id")
                filename = record.get("attachment_title") or file_id

                logger.info("-" * 60)
                logger.info("Processing Staging Record ID: %s", staging_record_id)
                logger.info("  File ID: %s | Title: %s", file_id, filename)

                if not staging_record_id:
                    logger.error("Missing mandatory staging_record_id. Skipping record.")
                    continue

                if not file_id:
                    error_msg = "Record missing target file_id reference"
                    logger.error(error_msg)
                    staging_client.update_status(staging_record_id, "failed", error_msg)
                    results.append({
                        "staging_record_id": staging_record_id,
                        "filename": filename,
                        "status": "failed",
                        "reason": error_msg,
                    })
                    continue

                # Transition status: pending -> processing
                try:
                    staging_client.update_status(staging_record_id, "processing")
                    logger.info("Record %s state updated → 'processing'", staging_record_id)
                except Exception as exc:
                    logger.exception("Failed updating state to 'processing' for ID: %s", staging_record_id)
                    results.append({
                        "staging_record_id": staging_record_id,
                        "filename": filename,
                        "status": "failed",
                        "reason": str(exc),
                    })
                    continue

                local_path: Optional[Path] = None
                try:
                    logger.info("Downloading asset %s from FileNest...", file_id)
                    local_path = Path(downloader.download_to_temp(file_id, filename=filename))
                    logger.info("Download completed → %s", local_path)

                    file_record = {
                        "staging_record_id": staging_record_id,
                        "filenest_file_id": file_id,
                        "filename": filename,
                        "filepath": str(local_path),
                        "content_type": record.get("attachment_content_type"),
                        "size_bytes": record.get("attachment_size"),
                        "patient_id": record.get("patient_id"),
                        "encounter_id": record.get("encounter_id"),
                        "service_request_id": record.get("service_request_id"),
                    }

                    # Execute extraction, classification, and transformation
                    result = process_one_file(file_record)

                    if result.get("status") != "processed":
                        error_msg = result.get("reason", "Unknown file transformation error")
                        logger.error("Processing failed for %s: %s", filename, error_msg)
                        staging_client.update_status(staging_record_id, "failed", error_msg)
                        results.append({"staging_record_id": staging_record_id, **result})
                        continue

                    # Patch successful findings back to the SAME staging record.
                    # Observations must be mapped to the fhir-staging ObservationInput
                    # shape (code_display, value_quantity_*, category coding, ...).
                    from src.components.fhir_staging.mapper import StagingObservationMapper

                    observations = [
                        StagingObservationMapper().map(obs)
                        for obs in result.get("observations", [])
                        if isinstance(obs, dict)
                    ]
                    patch_payload = {
                        "status": "completed",
                        "updated_by": "aiplatform-agent",
                        "observations": observations,
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    }

                    updated = staging_client.patch_staging_record(
                        staging_record_id,
                        patch_payload,
                    )
                    logger.info("Staging record %s successfully updated → 'completed'", staging_record_id)

                    result["staging_record_id"] = staging_record_id
                    result["staging_status"] = updated.get("status", "completed")
                    results.append(result)

                except Exception as exc:
                    logger.exception("Unhandled error processing record %s", staging_record_id)
                    err_str = f"Internal processing error: {exc}"
                    try:
                        staging_client.update_status(staging_record_id, "failed", err_str)
                    except Exception:
                        logger.exception("Failed updating status to 'failed' for %s", staging_record_id)

                    results.append({
                        "staging_record_id": staging_record_id,
                        "filename": filename,
                        "status": "failed",
                        "reason": err_str,
                    })

                finally:
                    # Clean up the temporary file after processing finishes
                    if local_path and local_path.exists():
                        try:
                            local_path.unlink()
                            logger.info("Removed temporary file: %s", local_path)
                        except Exception as cleanup_err:
                            logger.warning("Failed removing temp file %s: %s", local_path, cleanup_err)

    finally:
        try:
            downloader.close()
        except Exception:
            logger.warning("Error closing FileNest downloader client.", exc_info=True)

    logger.info("Task execution finished.")
    return results


# ===========================================================================
# DAG DEFINITION
# ===========================================================================

with DAG(
    "filenest_asset_consumer",
    default_args={
        "owner": "alpha_team",
        "retries": cfg.get("pipeline", {}).get("retries", 1),
        "retry_delay": timedelta(
            minutes=cfg.get("pipeline", {}).get("retry_delay_minutes", 5)
        ),
    },
    start_date=datetime(2026, 1, 1),
    schedule=[medical_files_asset],
    catchup=False,
    description=(
        "Consumes FileNest Assets, downloads files to managed temporary storage, "
        "runs medical extractions/transformations, and updates fhir-staging records."
    ),
    tags=[
        "filenest",
        "asset",
        "consumer",
        "medical",
        "fhir-staging",
    ],
) as dag:
    processing_task = PythonOperator(
        task_id="medical_extract_transform_task",
        python_callable=medical_processing,
    )