"""
Module: Clinical Document Indexing Consumer DAG

Purpose:
    Consumes the `clinical_document_ready` asset and indexes Clinical
    Domain Model JSON into OpenSearch for document-based medical chat.

Pipeline:
    1. Asset Trigger: Receives `clinical_document_ready` event.
    2. Scan: Lists Clinical JSON files under `indexing.input_dir`.
    3. Skip: Loads the processed-state file and skips already-indexed files.
    4. Index: For each new file — chunk → Jina embed → OpenSearch upsert
       (idempotent: deterministic chunk ids upsert, never duplicate).
    5. Record: Marks the file as processed in the state file.

The indexing layer (chunker/embedder/repository) is built by
IndexingFactory from PipelineConfig — same factories/config conventions as
the rest of the platform. FHIR-staging mapping stays fully independent.

Dependencies:
    - src.components.indexing.factory.IndexingFactory
    - src.components.utils.config.PipelineConfig
"""
    
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Airflow SDK Imports
# ---------------------------------------------------------------------------

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import Asset

from src.components.indexing.factory import IndexingFactory
from src.components.utils.config import PipelineConfig
from src.components.utils.reader import load_yml


# ---------------------------------------------------------------------------
# Configuration Setup
# ---------------------------------------------------------------------------

CONFIG_PATH: Path = Path(__file__).parent / "config" / "config.yml"
cfg: dict[str, Any] = load_yml(CONFIG_PATH)

# ---------------------------------------------------------------------------
# Asset
# ---------------------------------------------------------------------------

clinical_document_ready = Asset(
    name=cfg.get("asset", {}).get("name", "clinical_document_ready"),
    uri=cfg.get("asset", {}).get("uri", "file:///clinical/documents/ready"),
    group=cfg.get("asset", {}).get("group", "indexing"),
)

def fetch_clinical_document(
    patient_id: str,
    file_id: str,
) -> dict[str, Any]:
    """Retrieve the transformed Clinical Domain Model document.

    IMPORTANT:
        This function intentionally does NOT read from the local
        transformed directory.

    The actual implementation must use the document API/repository
    used by your platform to retrieve the transformed document using:

        patient_id
        file_id

    Expected return:

        {
            "patient_id": "...",
            "filenest_file_id": "...",
            "source_file": "...",
            "report_type": "...",
            "observations": [...],
            "diagnoses": [...],
            "summary": "...",
            ...
        }

    Replace the body of this function with your colleague's existing
    document retrieval client/method.
    """
    # ----------------------------------------------------------------------
    # IMPORTANT:
    # Do not put local file reading here.
    #
    # Example of the expected integration:
    #
    # document_client = DocumentClient(...)
    #
    # return document_client.get_document(
    #     patient_id=patient_id,
    #     file_id=file_id,
    # )
    # ----------------------------------------------------------------------

    raise NotImplementedError(
        "Connect fetch_clinical_document() to the existing "
        "Clinical Document API/repository that retrieves the "
        "transformed document using patient_id and file_id."
    )


# ============================================================================
# ASSET EVENT EXTRACTION
# ============================================================================


def get_clinical_document_event(
    inlet_events: Any,
) -> dict[str, Any]:
    """Extract the latest clinical_document_ready Asset event.

    Expected event.extra:

        {
            "patient_id": "...",
            "file_id": "..."
        }

    Airflow 3 asset-aware task context provides inlet events to the
    PythonOperator through `inlet_events`.

    The exact event object can vary slightly depending on the Airflow
    SDK version, so this function handles the common forms.
    """
    if not inlet_events:
        raise ValueError(
            "No inlet asset events were provided to the indexing task."
        )

    logger.info(
        "Available inlet assets: %s",
        (
            list(inlet_events.keys())
            if hasattr(inlet_events, "keys")
            else type(inlet_events)
        ),
    )

    # ----------------------------------------------------------------------
    # Find the event for clinical_document_ready
    # ----------------------------------------------------------------------

    event = None
    asset_name = clinical_document_ready.name

    # Dictionary-like access
    if hasattr(inlet_events, "get"):
        event = inlet_events.get(asset_name)

    # Some Airflow versions expose Asset as the key
    if event is None and hasattr(inlet_events, "get"):
        try:
            event = inlet_events.get(clinical_document_ready)
        except Exception:
            pass

    if event is None:
        raise ValueError(
            f"No event found for asset '{asset_name}'. Available events: "
            f"{list(inlet_events.keys()) if hasattr(inlet_events, 'keys') else inlet_events}"
        )

    # ----------------------------------------------------------------------
    # Event may be a list/collection. We need the latest event.
    # ----------------------------------------------------------------------

    if isinstance(event, (list, tuple)):
        if not event:
            raise ValueError(
                f"No events available for asset '{asset_name}'."
            )
        event = event[-1]

    # ----------------------------------------------------------------------
    # Extract event.extra
    # ----------------------------------------------------------------------

    extra = getattr(event, "extra", None)

    if extra is None and isinstance(event, dict):
        extra = event.get("extra")

    if not extra:
        raise ValueError(
            "clinical_document_ready event does not contain 'extra' metadata."
        )

    if not isinstance(extra, dict):
        raise ValueError(
            f"Invalid asset event extra type: {type(extra)}"
        )

    logger.info(
        "clinical_document_ready event metadata: %s",
        extra,
    )

    return extra


# ============================================================================
# INDEX ONE DOCUMENT
# ============================================================================


async def index_document(
    document: dict[str, Any],
    indexer: Any,
    patient_id: str,
    file_id: str,
) -> dict[str, Any]:
    """Execute:

    Clinical Document
          ↓
        Chunk
          ↓
    Jina Embedding
          ↓
     OpenSearch
    """
    if not patient_id:
        raise ValueError("patient_id is required for indexing.")

    if not file_id:
        raise ValueError("file_id is required for indexing.")

    metadata = {
        "patient_id": patient_id,
        "file_id": file_id,
        "source_file": document.get("source_file"),
        "report_type": document.get("report_type"),
        "encounter_id": document.get("encounter_id"),
        "service_request_id": document.get("service_request_id"),
    }

    logger.info("=" * 70)
    logger.info("Starting Clinical Document Indexing")
    logger.info("patient_id=%s", patient_id)
    logger.info("file_id=%s", file_id)
    logger.info("source_file=%s", document.get("source_file"))
    logger.info("report_type=%s", document.get("report_type"))

    # ----------------------------------------------------------------------
    # Chunk → Jina → OpenSearch
    # ----------------------------------------------------------------------

    summary = await indexer.index(
        document,
        metadata,
    )

    logger.info("Clinical document indexed successfully")
    logger.info(
        "file_id=%s | chunks=%s | embeddings=%s | indexed=%s",
        file_id,
        summary.get("chunks"),
        summary.get("embeddings"),
        summary.get("indexed"),
    )

    return {
        "patient_id": patient_id,
        "file_id": file_id,
        **summary,
    }


# ============================================================================
# RESOURCE CLEANUP
# ============================================================================


async def close_indexer(
    indexer: Any,
) -> None:
    """Close asynchronous resources while the asyncio event loop is still alive."""
    # ----------------------------------------------------------------------
    # Preferred: Indexer.close()
    # ----------------------------------------------------------------------

    close_method = getattr(indexer, "close", None)

    if close_method is not None:
        try:
            result = close_method()
            if asyncio.iscoroutine(result):
                await result

            logger.info("Indexing resources closed.")
            return

        except Exception:
            logger.exception("Failed to close indexer.")

    # ----------------------------------------------------------------------
    # Fallback: embedder.close()
    # ----------------------------------------------------------------------

    embedder = getattr(indexer, "_embedder", None)

    if embedder is None:
        return

    close_method = getattr(embedder, "close", None)

    if close_method is None:
        return

    try:
        result = close_method()
        if asyncio.iscoroutine(result):
            await result

        logger.info("Embedding resources closed.")

    except Exception:
        logger.exception("Failed to close embedding resources.")


# ============================================================================
# ASYNC INDEXING WORKFLOW
# ============================================================================


async def _run_indexing(
    patient_id: str,
    file_id: str,
    indexer: Any,
) -> dict[str, Any]:
    """Complete indexing workflow for one Clinical document.

    Workflow:

        patient_id + file_id
                ↓
        retrieve Clinical JSON
                ↓
             indexer
                ↓
        Chunk → Jina → OpenSearch
    """
    try:
        # ------------------------------------------------------------------
        # Retrieve transformed Clinical document
        # ------------------------------------------------------------------

        logger.info(
            "Retrieving Clinical document | patient_id=%s | file_id=%s",
            patient_id,
            file_id,
        )

        document = fetch_clinical_document(
            patient_id=patient_id,
            file_id=file_id,
        )

        if not document:
            raise ValueError(
                f"Clinical document is empty for patient_id={patient_id}, file_id={file_id}"
            )

        logger.info(
            "Clinical document retrieved successfully | patient_id=%s | file_id=%s",
            patient_id,
            file_id,
        )

        # ------------------------------------------------------------------
        # Index
        # ------------------------------------------------------------------

        return await index_document(
            document=document,
            indexer=indexer,
            patient_id=patient_id,
            file_id=file_id,
        )

    finally:
        await close_indexer(indexer)


# ============================================================================
# AIRFLOW TASK
# ============================================================================


def index_clinical_documents(
    **kwargs: Any,
) -> dict[str, Any]:
    """Airflow PythonOperator entrypoint.

    Trigger:
        clinical_document_ready

    Reads:
        patient_id
        file_id
    from the Asset event metadata.

    Then:
        retrieve document
            ↓
        chunk
            ↓
        Jina embedding
            ↓
        OpenSearch
    """
    logger.info("Clinical document ready asset triggered.")

    # ----------------------------------------------------------------------
    # Get inlet events
    # ----------------------------------------------------------------------

    inlet_events = kwargs.get("inlet_events")

    if inlet_events is None:
        raise ValueError(
            "Airflow did not provide inlet_events. "
            "Make sure this DAG is scheduled from clinical_document_ready."
        )

    # ----------------------------------------------------------------------
    # Extract Asset event
    # ----------------------------------------------------------------------

    event_data = get_clinical_document_event(inlet_events)

    # ----------------------------------------------------------------------
    # Extract identifiers
    # ----------------------------------------------------------------------

    patient_id = event_data.get("patient_id")
    file_id = event_data.get("file_id")

    if not patient_id:
        raise ValueError("clinical_document_ready event is missing patient_id.")

    if not file_id:
        raise ValueError("clinical_document_ready event is missing file_id.")

    logger.info(
        "Received Clinical document event | patient_id=%s | file_id=%s",
        patient_id,
        file_id,
    )

    # ----------------------------------------------------------------------
    # Create indexing stack
    # ----------------------------------------------------------------------

    config = PipelineConfig()

    if not config.indexing_enabled:
        raise RuntimeError(
            "Indexing is not configured. Set JINA_API_KEY and OPENSEARCH_* in .env."
        )

    indexer = IndexingFactory.create_indexer(config)

    logger.info("Indexing stack created successfully.")

    # ----------------------------------------------------------------------
    # Execute ONE asyncio event loop
    # ----------------------------------------------------------------------

    return asyncio.run(
        _run_indexing(
            patient_id=patient_id,
            file_id=file_id,
            indexer=indexer,
        )
    )


# ============================================================================
# DAG
# ============================================================================


with DAG(
    "clinical_document_indexer",
    default_args={
        "owner": "alpha_team",
        "retries": cfg.get("pipeline", {}).get("retries", 1),
        "retry_delay": timedelta(
            minutes=cfg.get("pipeline", {}).get("retry_delay_minutes", 5)
        ),
    },
    start_date=datetime(2026, 1, 1),
    # IMPORTANT:
    # This DAG runs only when clinical_document_ready is emitted.
    schedule=[clinical_document_ready],
    catchup=False,
    description=(
        "Consumes clinical_document_ready events, retrieves the "
        "Clinical Domain document using patient_id and file_id, "
        "generates Jina embeddings, and indexes chunks into OpenSearch."
    ),
    tags=[
        "indexing",
        "embedding",
        "opensearch",
        "document-chat",
    ],
) as dag:

    indexing_task = PythonOperator(
        task_id="index_clinical_documents",
        python_callable=index_clinical_documents,
    )


