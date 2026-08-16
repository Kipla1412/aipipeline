"""
Module: EMR Staging Pipeline DAG (Airflow Orchestration)
Purpose:
    NAS watch → PDF/DICOM extract → LLM classify → LLM transform →
    Staging (create draft + submit for review).

    This is the staging/approved-version approach: the MedicalTransformer
    produces a Clinical Domain Model, which is staged as a DraftClinicalRecord
    and submitted for human review.  The review and approve steps are
    Human-in-the-Loop and happen in the EMR review tool / CLI, not here.

Schedule: daily, watches for new PDFs/DICOMs in the NAS directory.
"""

import sys
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
from airflow.providers.standard.operators.python import PythonOperator
from typing import Any, List, Dict

from src.components.connectors.nas import NASConnector
from src.components.extractors.pymu_extractor import PyMuPdfExtractor
from src.components.extractors.dicom import DicomExtractor
from src.components.transformers.medical_transformer import MedicalTransformer
from src.components.transformers.medical_classifier import MedicalClassifier
from src.components.emr.staging.service import StagingService
from src.components.utils.reader import load_yml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config" / "staging.yml"


def load_config() -> dict:
    """Load the staging DAG YAML configuration."""
    return load_yml(CONFIG_PATH)


def _get_processed_files(staging_dir: str) -> set:
    """
    Purpose:
        Returns source stems already staged (dedup against staging dir).

    Args:
        staging_dir: Directory where draft JSON records live.

    Returns:
        set: Stems of already-staged source files.
    """
    output = Path(staging_dir)
    if not output.exists():
        return set()
    return {f.stem for f in output.glob("*.json")}


def fetch_openai_credentials(**kwargs: Any) -> dict:
    """
    Purpose:
        Retrieves the OpenAI API key from Airflow Variables.

    Returns:
        dict: {'api_key': key}.

    Raises:
        RuntimeError: If OPENAI_API_KEY is not set in Airflow Variables.
    """
    from airflow.models.variable import Variable
    api_key = Variable.get("OPENAI_API_KEY", default_var="")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in Airflow Variables (Admin → Variables)")
    return {"api_key": api_key}


def scan_nas(**kwargs: Any) -> List[str]:
    """
    Purpose:
        Scans the NAS directory for new PDFs/DICOMs not yet staged.

    Returns:
        list: New file paths to process.
    """
    cfg = load_config()
    nas_cfg = cfg.get("nas", {})
    staging_cfg = cfg.get("staging", {})

    pdf_dir = Path(nas_cfg.get("directory", "/opt/airflow/data/storage/raw"))
    ext = nas_cfg.get("allowed_extensions", [".pdf", ".dcm"])
    stg_cfg = staging_cfg.get("staging_dir", "storage/emr/staging")
    staging_dir = stg_cfg if os.path.isabs(stg_cfg) else os.path.join(_AI_PLATFORM, stg_cfg)

    config = {"nas_dir_path": str(pdf_dir), "allowed_extensions": ext}
    connector = NASConnector(config)

    async def _run():
        session = await connector.connect()
        return list(session.get_new_files())

    import asyncio
    all_files = asyncio.run(_run())

    processed = _get_processed_files(staging_dir)
    new_files = [f for f in all_files if f.stem not in processed]
    logger.info(f"Found {len(all_files)} file(s), {len(new_files)} new for staging")
    return [str(f) for f in new_files]


def extract_classify_transform(**kwargs: Any) -> List[Dict[str, Any]]:
    """
    Purpose:
        Extracts text from PDFs/DICOMs, classifies report type,
        and transforms into a Clinical Domain Model.

    Returns:
        list: Transformed document dicts ready for staging.
    """
    creds = kwargs["ti"].xcom_pull(task_ids="fetch_credentials_task")
    file_paths = kwargs["ti"].xcom_pull(task_ids="scan_nas_task") or []
    if not file_paths:
        logger.info("No new files — skipping.")
        return []

    cfg = load_config()
    ext_cfg = cfg.get("extraction", {})
    cls_cfg = cfg.get("classification", {})
    trans_cfg = cfg.get("transformation", {})
    img_out = ext_cfg.get("image_output_dir", "storage/images")
    img_out = img_out if os.path.isabs(img_out) else os.path.join(_AI_PLATFORM, img_out)

    pdf_extractor = PyMuPdfExtractor({
        "extract_images": ext_cfg.get("extract_images", False),
        "output_image_dir": img_out,
    })
    dicom_extractor = DicomExtractor({
        "output_image_dir": img_out,
        "extract_preview": True,
    })
    classifier = MedicalClassifier({
        "api_key": creds["api_key"],
        "model": cls_cfg.get("model", "gpt-4o-mini"),
    })
    transformer = MedicalTransformer({
        "api_key": creds["api_key"],
        "model": trans_cfg.get("model", "gpt-4o-mini"),
    })

    async def _run():
        documents = []
        for fp in file_paths:
            path = Path(fp)
            suffix = path.suffix.lower()
            is_dicom = suffix in (".dcm", ".dicom")

            extracted = dicom_extractor.extract(fp) if is_dicom else pdf_extractor.extract(fp)
            report_type = await classifier.classify(extracted.markdown)

            doc = await transformer.transform(
                extracted.markdown,
                dicom_metadata=extracted.dicom_metadata if is_dicom else None,
            )
            doc["report_type"] = report_type
            doc["source_file"] = path.name
            documents.append(doc)
            logger.info(f"Transformed: {doc.get('patient_name')} [{report_type}] "
                        f"({len(doc.get('observations', []))} obs)")

        return documents

    import asyncio
    return asyncio.run(_run())


def stage_for_review(**kwargs: Any) -> List[str]:
    """
    Purpose:
        Creates a DraftClinicalRecord for each transformed document and
        submits it for human review (PENDING_REVIEW state).

    Returns:
        list: Record IDs of newly staged drafts.
    """
    docs = kwargs["ti"].xcom_pull(task_ids="extract_classify_transform_task") or []
    if not docs:
        return []

    cfg = load_config()
    stg_cfg = cfg.get("staging", {}).get("staging_dir", "storage/emr/staging")
    staging_dir = stg_cfg if os.path.isabs(stg_cfg) else os.path.join(_AI_PLATFORM, stg_cfg)

    service = StagingService(staging_dir=staging_dir)
    record_ids = []
    for doc in docs:
        draft = service.create_draft(doc, doc.get("source_file", ""))
        draft = service.submit_for_review(draft.record_id)
        record_ids.append(draft.record_id)
        logger.info(f"Staged for review: {draft.record_id} ({doc.get('patient_name')})")

    logger.info(f"Staged {len(record_ids)} record(s) for review — READY FOR HITL REVIEW")
    return record_ids


cfg = load_config()

default_args = {
    "owner": "alpha_team",
    "retries": cfg.get("pipeline", {}).get("retries", 1),
    "retry_delay": timedelta(minutes=cfg.get("pipeline", {}).get("retry_delay_minutes", 5)),
}

with DAG(
    "emr_staging_pipeline",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=cfg.get("pipeline", {}).get("schedule", "@daily"),
    catchup=False,
    description=cfg.get("pipeline", {}).get("description", "EMR Staging Pipeline"),
    tags=["emr", "clinical", "staging", "review"],
) as dag:

    fetch_credentials_task = PythonOperator(
        task_id="fetch_credentials_task",
        python_callable=fetch_openai_credentials,
    )

    scan_nas_task = PythonOperator(
        task_id="scan_nas_task",
        python_callable=scan_nas,
    )

    extract_classify_transform_task = PythonOperator(
        task_id="extract_classify_transform_task",
        python_callable=extract_classify_transform,
    )

    stage_for_review_task = PythonOperator(
        task_id="stage_for_review_task",
        python_callable=stage_for_review,
    )

    fetch_credentials_task >> scan_nas_task >> extract_classify_transform_task >> stage_for_review_task
