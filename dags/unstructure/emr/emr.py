"""
Module: EMR Transformer DAG (Airflow Orchestration)
Purpose:
    NAS watch → PDF/DICOM extract → LLM classify → LLM transform.

Stops at the Clinical Domain Model (ready for staging).
No staging, no review, no FHIR — that happens in the EMR staging area.

Schedule: daily, watches for new PDFs in NAS directory.
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
from airflow.providers.standard.operators.python import PythonOperator
from typing import Any, List

from src.components.connectors.nas import NASConnector
from src.components.extractors.pymu_extractor import PyMuPdfExtractor
from src.components.extractors.dicom import DicomExtractor
from src.components.transformers.medical_transformer import MedicalTransformer
from src.components.transformers.medical_classifier import MedicalClassifier
from src.components.utils.reader import load_yml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config" / "config.yml"


def load_config() -> dict:
    return load_yml(CONFIG_PATH)


def _get_processed_files(output_dir: str) -> set:
    """Return source filenames already transformed (dedup against output dir)."""
    output = Path(output_dir)
    if not output.exists():
        return set()
    return {f.stem for f in output.glob("*.json")}


def fetch_openai_credentials(**kwargs: Any) -> dict:
    from airflow.models.variable import Variable
    api_key = Variable.get("OPENAI_API_KEY", default_var="")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in Airflow Variables (Admin → Variables)")
    return {"api_key": api_key}


def scan_nas(**kwargs: Any) -> List[str]:
    cfg = load_config()
    nas_cfg = cfg.get("nas", {})
    out_cfg = cfg.get("transformation", {}).get("output_dir", "storage/emr/transformed")
    output_dir = out_cfg if os.path.isabs(out_cfg) else os.path.join(_AI_PLATFORM, out_cfg)

    pdf_dir = Path(nas_cfg.get("directory", "/opt/airflow/data/storage/raw"))
    ext = nas_cfg.get("allowed_extensions", [".pdf", ".dcm"])

    config = {"nas_dir_path": str(pdf_dir), "allowed_extensions": ext}
    connector = NASConnector(config)

    async def _run():
        session = await connector.connect()
        return list(session.get_new_files())

    import asyncio
    all_files = asyncio.run(_run())

    processed = _get_processed_files(output_dir)
    new_files = [f for f in all_files if f.stem not in processed]
    logger.info(f"Found {len(all_files)} file(s), {len(new_files)} new for transformation")
    return [str(f) for f in new_files]


def extract_and_transform(**kwargs: Any) -> List[dict]:
    creds = kwargs["ti"].xcom_pull(task_ids="fetch_credentials_task")
    file_paths = kwargs["ti"].xcom_pull(task_ids="scan_nas_task") or []
    if not file_paths:
        logger.info("No new files — skipping.")
        return []

    cfg = load_config()
    ext_cfg = cfg.get("extraction", {})
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
        "model": cfg.get("classification", {}).get("model", "gpt-4o-mini"),
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


def save_transformed(**kwargs: Any) -> None:
    """Save the Clinical Domain Model JSON to storage/emr/transformed/."""
    docs = kwargs["ti"].xcom_pull(task_ids="extract_and_transform_task") or []
    if not docs:
        return

    import json
    cfg = load_config()
    out_cfg = cfg.get("transformation", {}).get("output_dir", "storage/emr/transformed")
    output_dir = Path(out_cfg if os.path.isabs(out_cfg) else os.path.join(_AI_PLATFORM, out_cfg))
    output_dir.mkdir(parents=True, exist_ok=True)

    for doc in docs:
        source = doc.get("source_file", "unknown")
        path = output_dir / f"{Path(source).stem}.json"
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        logger.info(f"Saved Clinical Domain Model → {path}")

    logger.info(f"Saved {len(docs)} transformed record(s) to {output_dir}")


cfg = load_config()

default_args = {
    "owner": "alpha_team",
    "retries": cfg.get("pipeline", {}).get("retries", 1),
    "retry_delay": timedelta(minutes=cfg.get("pipeline", {}).get("retry_delay_minutes", 5)),
}

with DAG(
    "emr_transformer_pipeline",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=cfg.get("pipeline", {}).get("schedule", "@daily"),
    catchup=False,
    description=cfg.get("pipeline", {}).get("description", "EMR Transformer Pipeline"),
    tags=["emr", "clinical", "transformer"],
) as dag:

    fetch_credentials_task = PythonOperator(
        task_id="fetch_credentials_task",
        python_callable=fetch_openai_credentials,
    )

    scan_nas_task = PythonOperator(
        task_id="scan_nas_task",
        python_callable=scan_nas,
    )

    extract_and_transform_task = PythonOperator(
        task_id="extract_and_transform_task",
        python_callable=extract_and_transform,
    )

    save_transformed_task = PythonOperator(
        task_id="save_transformed_task",
        python_callable=save_transformed,
    )

    fetch_credentials_task >> scan_nas_task >> extract_and_transform_task >> save_transformed_task
