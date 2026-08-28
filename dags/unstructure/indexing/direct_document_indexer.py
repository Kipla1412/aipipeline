"""
Module: Direct Document Indexer DAG

Purpose:
    Directly indexes downloaded FileNest documents into OpenSearch for
    document-based medical chat. Triggered by the existing
    ``medical_files_asset``.

    This DAG is ONLY an orchestration layer. It reuses the existing
    extractor, embedding, and OpenSearch modules via their factories:

        medical_files_asset (asset event)
            ↓
        event metadata (file_id, patient_id, filename, filepath, content_type)
            ↓
        downloaded file path
            ↓
        ExtractorFactory (pdf / image / dicom)
            ↓
        extracted.markdown
            ↓
        validate (non-empty)
            ↓
        IndexingFactory.create_indexer(PipelineConfig())
            ↓
        indexer.index(content, metadata)
            ↓
        existing chunker → Jina embedding → OpenSearch repository

    No classification, no Clinical Domain transformation, no FHIR-staging
    interaction, and no transformed-JSON output — direct indexing only.

Dependencies:
    - src.components.extractors.factory.ExtractorFactory
    - src.components.indexing.factory.IndexingFactory
    - src.components.utils.config.PipelineConfig
"""

from __future__ import annotations

import asyncio
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

from src.components.extractors.factory import ExtractorFactory
from src.components.indexing.factory import IndexingFactory
from src.components.utils.config import PipelineConfig
from src.components.utils.reader import load_yml


# ---------------------------------------------------------------------------
# Configuration Setup
# ---------------------------------------------------------------------------

CONFIG_PATH: Path = Path(__file__).parent / "config" / "config.yml"
cfg: dict[str, Any] = load_yml(CONFIG_PATH)

# The direct indexer shares the same asset identity as the filenest producer,
# so it reads the filenest DAG config for the asset definition.
_FILENEST_CONFIG_PATH: Path = (
    Path(__file__).resolve().parent.parent / "filenest" / "config" / "config.yml"
)
filenest_cfg: dict[str, Any] = load_yml(_FILENEST_CONFIG_PATH)


def _abs_path(value: str | None, default: Path) -> Path:
    """
    Purpose:
        Resolves a possibly-relative path from config.yml against the project
        root (_AI_PLATFORM) so Airflow workers never use the wrong CWD.

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
    if value.startswith("aiplatform/"):
        p = Path(value[len("aiplatform/"):])
    return _AI_PLATFORM / p


# ---------------------------------------------------------------------------
# Asset Definition (shared identity with the producer)
# ---------------------------------------------------------------------------

medical_files_asset = Asset(
    name=filenest_cfg.get("asset", {}).get("name", "medical_files_asset"),
    uri=filenest_cfg.get("asset", {}).get("uri", "file:///medical/files/available"),
    group=filenest_cfg.get("asset", {}).get("group", "filenest"),
)


# ===========================================================================
# DIRECT INDEXING ENGINE
# ===========================================================================


def _event_metadata(**kwargs: Any) -> list[dict[str, Any]]:
    """
    Purpose:
        Extracts per-file metadata from the triggering asset event(s).

        ``inlet_events`` returns all events recorded for the asset (ordered
        by timestamp), so this collects every event that carries file info.
        file_id values are sanitized (stripped / prefix removed) to tolerate
        malformed upstream data like " File ID: abc-123 ".

    Returns:
        list[dict]: One metadata dict per event with a usable file_id.
    """
    inlet_events = kwargs.get("inlet_events") or {}
    events = []
    for asset_key, asset_events in inlet_events.items():
        for event in asset_events:
            extra = getattr(event, "extra", None) or {}
            file_id = _sanitize_file_id(extra.get("file_id"))
            if not file_id:
                continue
            cleaned = dict(extra)
            cleaned["file_id"] = file_id
            events.append(cleaned)
    return events


def _sanitize_file_id(value: Any) -> str:
    """
    Purpose:
        Normalizes a file_id from event metadata, tolerating malformed
        upstream values (" File ID: abc-123 " → "abc-123").

    Returns:
        str: The cleaned file_id, or "" when no usable id is present.
    """
    if not value:
        return ""
    s = str(value).strip()
    # Strip a leading "File ID:" / "file id" label if present.
    for prefix in ("File ID:", "File id:", "file id:", "file_id:", "File:"):
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix):].strip()
            break
    return s.strip()


def _build_downloader(download_dir: Path) -> Any:
    """
    Purpose:
        Builds the existing FileNest downloader from the Airflow connection.

    Returns:
        FileNestDownloader: Ready-to-use downloader.
    """
    from src.components.credentials.factory import CredentialFactory

    conn_id = filenest_cfg.get("credentials", {}).get("filenest_conn_id", "filenest_conn_id")
    creds = CredentialFactory.get_provider(
        mode="airflow",
        conn_id=conn_id,
    ).get_credentials()

    api_key = creds.get("api_key")
    project_id = creds.get("project_id")
    base_url = creds.get("filenest_api_url") or creds.get("base_url") or creds.get("host")
    if base_url and not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"

    if not api_key or not project_id or not base_url:
        raise RuntimeError(
            f"FileNest credentials missing from Airflow connection '{conn_id}' "
            "(api_key, project_id, filenest_api_url)"
        )

    from src.components.connectors.factory import ConnectorFactory

    filenest = ConnectorFactory.get_connector(
        "filenest",
        {"api_key": api_key, "project_id": project_id, "base_url": base_url},
    )
    downloader = ExtractorFactory.get_extractor(
        "filenest",
        connection=filenest,
        config={"download_dir": str(download_dir)},
    )
    return downloader


def _resolve_filepath(
    event: dict[str, Any],
    download_dir: Path,
    downloader: Any | None = None,
) -> Path:
    """
    Purpose:
        Resolves the actual file to process for an event.

        Prefers the event's explicit ``filepath``; otherwise looks for the
        file under the managed download directory by filename; finally, if a
        downloader is available, downloads the file by ``file_id``.

    Returns:
        Path: The resolved local file path.

    Raises:
        FileNotFoundError: If no usable path can be resolved.
    """
    filepath = event.get("filepath")
    if filepath:
        p = Path(filepath)
        if p.exists():
            return p

    filename = event.get("filename")
    if filename:
        candidate = download_dir / Path(filename).name
        if candidate.exists():
            return candidate

    file_id = event.get("file_id")
    if downloader is not None and file_id:
        try:
            path = downloader.download_to_temp(file_id, filename=filename)
            return Path(path)
        except Exception as exc:
            raise FileNotFoundError(
                f"Could not download file_id={file_id} from FileNest: {exc}"
            ) from exc

    raise FileNotFoundError(f"Could not locate downloaded file for event: {event}")


def _select_extractor(filepath: Path, images_dir: Path, openai_api_key: str | None) -> tuple[str, dict[str, Any]]:
    """
    Purpose:
        Picks the extractor type + config based on the file extension.

    Args:
        filepath (Path): The file to extract.
        images_dir (Path): Where extracted images are saved.
        openai_api_key (str | None): OpenAI key for image analysis
            (from the Airflow 'openai' connection; .env as fallback).

    Returns:
        tuple[str, dict]: (extractor_type, extractor_config).

    Raises:
        ValueError: If the file type is not supported.
    """
    suffix = filepath.suffix.lower()
    if suffix == ".pdf":
        return "pdf", {
            "extract_images": True,
            "output_image_dir": str(images_dir),
        }
    if suffix in (".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"):
        return "image", {
            "api_key": openai_api_key or "",
            "model_name": "gpt-4o",
        }
    if suffix == ".dcm":
        return "dicom", {
            "output_image_dir": str(images_dir),
            "extract_preview": True,
        }
    raise ValueError(f"Unsupported file type for direct indexing: {suffix}")


def _extract_content(extractor_type: str, extractor_config: dict[str, Any], filepath: Path) -> str:
    """
    Purpose:
        Runs the existing extractor for the detected file type (sync call).

    Returns:
        str: Extracted markdown text (non-empty).

    Raises:
        ValueError: If extraction produced no usable content.
    """
    extractor = ExtractorFactory.get_extractor(extractor_type, config=extractor_config)

    if extractor_type == "image":
        # ImageAnalyzer.extract is async and takes a list of image paths.
        markdown = asyncio.run(extractor.extract([str(filepath)]))
    else:
        result = extractor.extract(str(filepath))
        markdown = getattr(result, "markdown", "") or ""

    text = (markdown or "").strip()
    if not text:
        raise ValueError(f"Extraction produced no usable content for {filepath.name}")
    return text


async def _index_one(indexer: Any, text: str, filepath: Path, event: dict[str, Any]) -> dict[str, Any]:
    """
    Purpose:
        Indexes a single extracted document via the existing indexer.

    Returns:
        dict: Indexing summary (chunks, embeddings, indexed, ...).
    """
    metadata = {
        "file_id": event.get("file_id"),
        "patient_id": event.get("patient_id"),
        "source_file": event.get("filename") or filepath.name,
        "content_type": event.get("content_type"),
    }
    logger.info("Indexing started for %s", filepath.name)
    result = await indexer.index(
        {"summary": text, "sections": None, "diagnoses": [], "observations": [], "medications": [], "procedures": [], "imaging": None},
        metadata,
    )
    logger.info(
        "Indexing completed for %s — chunks=%d embeddings=%d indexed=%d",
        filepath.name,
        result.get("chunks", 0),
        result.get("embeddings", 0),
        result.get("indexed", 0),
    )
    return {**result, "file": filepath.name}


def _fetch_openai_api_key() -> str | None:
    """
    Purpose:
        Fetches the OpenAI API key from the Airflow 'openai' connection,
        falling back to the local PipelineConfig (.env) when the
        connection is not configured.

    Returns:
        str | None: The API key, or None when unavailable.
    """
    from src.components.credentials.factory import CredentialFactory

    conn_id = cfg.get("credentials", {}).get("openai_conn_id", "openai")
    try:
        creds = CredentialFactory.get_provider(
            mode=cfg.get("credentials", {}).get("mode", "airflow"),
            conn_id=conn_id,
        ).get_credentials()
        key = creds.get("api_key") or creds.get("password") or creds.get("token")
        if not key:
            login = creds.get("login")
            if login and str(login).startswith("sk-"):
                key = login
        if key:
            logger.info("OpenAI credentials loaded from Airflow connection '%s'", conn_id)
            return str(key)
    except Exception:
        logger.warning("OpenAI Airflow connection '%s' not found — falling back to .env", conn_id)

    fallback = PipelineConfig().OPENAI_API_KEY
    return fallback or None


def _build_indexer_config() -> PipelineConfig:
    """
    Purpose:
        Builds a PipelineConfig with Jina/OpenSearch credentials sourced
        from Airflow Connections (falling back to .env values).

        Connection mapping (Airflow → config):
            jina:       api_key (extra)  → JINA_API_KEY
                        host             → JINA_BASE_URL
            opensearch: login            → OPENSEARCH_LOGIN
                        password         → OPENSEARCH_PASSWORD
                        host             → OPENSEARCH_HOST
                        port             → OPENSEARCH_PORT
                        schema (extra)   → OPENSEARCH_SCHEMA

    Returns:
        PipelineConfig: Config ready for IndexingFactory.create_indexer.
    """
    from src.components.credentials.factory import CredentialFactory

    config = PipelineConfig()
    mode = cfg.get("credentials", {}).get("mode", "airflow")

    # --- Jina ---
    jina_conn_id = cfg.get("credentials", {}).get("jina_conn_id", "jina_api")
    try:
        jina_creds = CredentialFactory.get_provider(mode=mode, conn_id=jina_conn_id).get_credentials()

        # The API key may live in the Extra as api_key/token/password, or inside
        # a headers dict as "Authorization: Bearer <key>".
        jina_api_key = (
            jina_creds.get("api_key")
            or jina_creds.get("token")
            or jina_creds.get("password")
        )
        if not jina_api_key:
            headers = jina_creds.get("headers")
            if isinstance(headers, dict):
                auth = headers.get("Authorization") or headers.get("authorization")
                if auth and str(auth).lower().startswith("bearer "):
                    jina_api_key = str(auth)[len("bearer "):].strip()
        if not jina_api_key:
            login = jina_creds.get("login")
            if login and str(login).startswith("jina_"):
                jina_api_key = login
        if jina_api_key:
            config.JINA_API_KEY = jina_api_key

        # Prefer the connection's base_url when present; otherwise build from
        # host, tolerating an already-schemed value. The embedder posts to the
        # relative path "embeddings", so the base must end at "/v1/" — strip a
        # trailing "/embeddings" if the connection includes it.
        jina_base = jina_creds.get("base_url")
        if jina_base:
            base = str(jina_base).strip().rstrip("/")
            if base.endswith("/embeddings"):
                base = base[: -len("/embeddings")]
            config.JINA_BASE_URL = base.rstrip("/") + "/"
        else:
            jina_host = jina_creds.get("host")
            if jina_host:
                host = jina_host.strip().rstrip("/")
                if not host.startswith(("http://", "https://")):
                    host = f"https://{host}"
                config.JINA_BASE_URL = f"{host}/v1/"
        logger.info("Jina credentials loaded from Airflow connection '%s'", jina_conn_id)
    except Exception:
        logger.warning("Jina Airflow connection '%s' not found — falling back to .env", jina_conn_id)

    # --- OpenSearch ---
    os_conn_id = cfg.get("credentials", {}).get("opensearch_conn_id", "opensearch_api")
    try:
        os_creds = CredentialFactory.get_provider(mode=mode, conn_id=os_conn_id).get_credentials()
        if os_creds.get("login"):
            config.OPENSEARCH_LOGIN = os_creds["login"]
        if os_creds.get("password"):
            config.OPENSEARCH_PASSWORD = os_creds["password"]
        if os_creds.get("host"):
            config.OPENSEARCH_HOST = os_creds["host"]
        if os_creds.get("port"):
            config.OPENSEARCH_PORT = int(os_creds["port"])
        if os_creds.get("schema") and os_creds["schema"].lower() in ("http", "https"):
            config.OPENSEARCH_SCHEMA = os_creds["schema"].lower()
        logger.info("OpenSearch credentials loaded from Airflow connection '%s'", os_conn_id)
    except Exception:
        logger.warning("OpenSearch Airflow connection '%s' not found — falling back to .env", os_conn_id)

    return config


def index_documents(**kwargs: Any) -> list[dict[str, Any]]:
    """
    Purpose:
        Main Airflow PythonOperator task: read the asset event metadata,
        extract the downloaded document, and index it via the existing
        IndexingFactory (chunk → Jina embed → OpenSearch).

        One asyncio event loop is used for the whole indexing operation.

    Returns:
        list[dict]: Per-file indexing summaries.

    Raises:
        FileNotFoundError: If no event metadata or downloaded file is found.
    """
    logger.info("Direct document indexer triggered by medical_files_asset")

    events = _event_metadata(**kwargs)
    if not events:
        # The producer emits the asset every minute; it only carries file
        # metadata when pending records exist. An empty event = no work.
        logger.info("No file metadata in asset event — nothing to index")
        return []

    download_dir = _abs_path(
        cfg.get("indexing", {}).get("temp_dir"),
        _AI_PLATFORM / "storage" / "temp",
    )
    download_dir.mkdir(parents=True, exist_ok=True)

    # Extracted images go into a temporary folder under temp/ so they are
    # treated as disposable artifacts like the downloaded documents.
    images_dir = _abs_path(
        cfg.get("indexing", {}).get("images_dir"),
        _AI_PLATFORM / "storage" / "temp" / "images",
    )
    images_dir.mkdir(parents=True, exist_ok=True)

    openai_api_key = _fetch_openai_api_key()

    config = _build_indexer_config()
    if not config.indexing_enabled:
        raise RuntimeError(
            "Indexing not configured — set JINA_API_KEY and OPENSEARCH_* "
            "in .env or add the 'jina'/'opensearch' Airflow connections"
        )

    indexer = IndexingFactory.create_indexer(config)
    downloader = None
    try:
        downloader = _build_downloader(download_dir)
    except Exception as exc:
        # The downloader is only needed when the file is not already on disk;
        # fail fast here since we cannot process files without it.
        logger.warning("Could not build FileNest downloader: %s", exc)
        raise

    async def _run_all() -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for event in events:
            file_id = event.get("file_id")
            patient_id = event.get("patient_id")
            filename = event.get("filename")
            content_type = event.get("content_type")
            logger.info(
                "Asset event → file_id=%s patient_id=%s filename=%s content_type=%s",
                file_id, patient_id, filename, content_type,
            )

            if not file_id:
                # The producer emits the asset every minute; only events that
                # carry a file_id represent actual work. Skip empty triggers.
                logger.info("Event has no file_id — skipping (no work)")
                continue

            filepath = _resolve_filepath(event, download_dir, downloader)
            logger.info("Extraction started for %s (%s)", filepath.name, filepath.suffix)

            extractor_type, extractor_config = _select_extractor(filepath, images_dir, openai_api_key)
            text = _extract_content(extractor_type, extractor_config, filepath)
            logger.info("Extraction completed — %d chars from %s", len(text), filepath.name)

            results.append(await _index_one(indexer, text, filepath, event))
        return results

    try:
        return asyncio.run(_run_all())
    finally:
        indexer.close()
        try:
            downloader.close()
        except Exception:
            logger.warning("Failed closing FileNest downloader", exc_info=True)
        logger.info("Cleanup completed — indexer and downloader closed")


# ===========================================================================
# DAG DEFINITION
# ===========================================================================

with DAG(
    "direct_document_indexer",
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
        "Direct document indexing: extract downloaded FileNest documents and "
        "index them into OpenSearch via the existing IndexingFactory."
    ),
    tags=[
        "filenest",
        "asset",
        "indexing",
        "opensearch",
        "document-chat",
    ],
) as dag:
    indexing_task = PythonOperator(
        task_id="index_downloaded_documents",
        python_callable=index_documents,
        inlets=[medical_files_asset],
    )
