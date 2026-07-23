"""
Module: Medical Pipeline DAG (Airflow Orchestration)
Purpose:
    NAS watch → PDF extract → LLM classify → LLM transform →
    Wiki Generator → Metadata Index → Knowledge Graph Builder.

Schedule: hourly, watches for new PDFs in NAS directory.
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
from pathlib import Path
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from typing import Any, Dict, List

from src.components.connectors.nas import NASConnector
from src.components.extractors.pymu_extractor import PyMuPdfExtractor
from src.components.extractors.image_analyzer import ImageAnalyzer
from src.components.transformers.medical_transformer import MedicalTransformer
from src.components.transformers.medical_classifier import MedicalClassifier
from src.components.generators.wiki_generator_wrapper import WikiGenerator
from src.components.metadata.json_repository import JsonMetadataRepository
from src.components.metadata.generator import MetadataGenerator
from src.components.graphbuilder.graphify_builder import GraphifyyBuilder
from src.components.utils.reader import load_yml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config" / "config.yml"
OPENAI_CONN_ID = "openai"


def load_config() -> dict:
    return load_yml(CONFIG_PATH)


import os

def fetch_openai_credentials(**kwargs: Any) -> Dict[str, str]:
    from airflow.models.variable import Variable
    api_key = Variable.get("OPENAI_API_KEY", default_var="")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in Airflow Variables (Admin → Variables)")
    logger.info("Using OPENAI_API_KEY from Airflow Variables.")
    return {"api_key": api_key}


def _get_processed_files(wiki_dir: str) -> set:
    import re
    log = Path(wiki_dir) / "log.md"
    if not log.exists():
        return set()
    text = log.read_text(encoding="utf-8")
    return set(re.findall(r"\*\*Source File:\*\*\s*\n\s*\n\s+(.+\.pdf)", text))


def scan_nas(**kwargs: Any) -> List[str]:
    cfg = load_config().get("nas", {})
    pdf_dir = Path(cfg.get("directory", "/opt/airflow/data/storage/pdf"))
    wiki_dir = cfg.get("wiki", {}).get("output_dir", "/opt/airflow/data/storage/wiki")
    ext = cfg.get("allowed_extensions", [".pdf"])
    config = {"nas_dir_path": str(pdf_dir), "allowed_extensions": ext}
    kwargs["ti"].xcom_push(key="pdf_dir", value=str(pdf_dir))
    connector = NASConnector(config)

    async def _run():
        session = await connector.connect()
        return [f for f in session.get_new_files()]

    import asyncio
    all_files = asyncio.run(_run())
    processed = _get_processed_files(wiki_dir)
    new_files = [f for f in all_files if f.name not in processed]
    skipped = len(all_files) - len(new_files)
    logger.info(f"Found {len(all_files)} PDF(s), {skipped} already processed, {len(new_files)} new")
    return [str(f) for f in new_files]


def extract_and_classify(**kwargs: Any) -> List[Dict[str, Any]]:
    creds = kwargs["ti"].xcom_pull(task_ids="fetch_credentials_task")
    file_paths = kwargs["ti"].xcom_pull(task_ids="scan_nas_task") or []
    if not file_paths:
        logger.info("No new PDFs — skipping.")
        return []

    cfg = load_config()
    ext_cfg = cfg.get("extraction", {})
    cls_cfg = cfg.get("classification", {})
    img_cfg = cfg.get("image_analysis", {})

    extractor = PyMuPdfExtractor({"extract_images": ext_cfg.get("extract_images", True),
                                   "output_image_dir": ext_cfg.get("image_output_dir", "storage/images")})

    async def _run():
        classifier = MedicalClassifier({"api_key": creds["api_key"], "model": cls_cfg.get("model", "gpt-4o-mini")})
        image_analyzer = ImageAnalyzer({"api_key": creds["api_key"], "model": img_cfg.get("model", "gpt-4o")})
        documents = []
        for fp in file_paths:
            logger.info(f"Extracting: {fp}")
            extracted = extractor.extract(fp)
            text = extracted.markdown
            if extracted.images:
                desc = await image_analyzer.extract(extracted.images)
                text = desc + "\n\n" + text
            report_type = await classifier.classify(extracted.markdown)
            documents.append({"filepath": fp, "text": text, "report_type": report_type, "images": extracted.images})
        return documents

    import asyncio
    return asyncio.run(_run())


def transform_documents(**kwargs: Any) -> List[Dict[str, Any]]:
    creds = kwargs["ti"].xcom_pull(task_ids="fetch_credentials_task")
    docs = kwargs["ti"].xcom_pull(task_ids="extract_and_classify_task")
    if not docs:
        return []

    cfg = load_config().get("transformation", {})
    transformer = MedicalTransformer({"api_key": creds["api_key"], "model": cfg.get("model", "gpt-4o-mini")})

    async def _run():
        import hashlib
        results = []
        for d in docs:
            structured = await transformer.transform(d["text"])
            h = hashlib.sha256(Path(d["filepath"]).name.encode()).hexdigest()[:12]
            structured["document_id"] = f"{Path(d['filepath']).stem}:{h}"
            structured["report_type"] = d["report_type"]
            structured["images"] = d["images"]
            structured["source_filename"] = Path(d["filepath"]).name
            results.append(structured)
            logger.info(f"Transformed: {structured.get('patient_name')} [{structured['report_type']}]")
        return results

    import asyncio
    return asyncio.run(_run())


def generate_wiki_and_metadata(**kwargs: Any) -> None:
    docs = kwargs["ti"].xcom_pull(task_ids="transform_documents_task")
    if not docs:
        return

    cfg = load_config()
    wiki_dir = Path(cfg.get("wiki", {}).get("output_dir", "/opt/airflow/data/storage/wiki"))
    meta_path = cfg.get("metadata", {}).get("index_path", "/opt/airflow/data/storage/metadata/index.json")

    wiki = WikiGenerator({"base_dir": str(wiki_dir)})
    meta_gen = MetadataGenerator()
    repo = JsonMetadataRepository(Path(meta_path))
    graph = GraphifyyBuilder({"target_dir": str(wiki_dir)})

    async def _run():
        for doc in docs:
            wiki.generate(doc, doc.get("source_filename", ""))
            for entry in meta_gen.generate(doc):
                await repo.upsert(entry)
        await repo._flush()
        try:
            graph.build_from_documents(docs)
            logger.info("Knowledge graph built.")
        except Exception as e:
            logger.error(f"Graph build failed: {e}")

    import asyncio
    asyncio.run(_run())


cfg = load_config()

default_args = {
    "owner": "alpha_team",
    "retries": cfg.get("pipeline", {}).get("retries", 1),
    "retry_delay": timedelta(minutes=cfg.get("pipeline", {}).get("retry_delay_minutes", 5)),
}

with DAG(
    "medical_pipeline",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=cfg.get("pipeline", {}).get("schedule", "@hourly"),
    catchup=False,
    description=cfg.get("pipeline", {}).get("description", "Medical Pipeline"),
) as dag:

    fetch_credentials_task = PythonOperator(
        task_id="fetch_credentials_task",
        python_callable=fetch_openai_credentials,
    )

    scan_nas_task = PythonOperator(
        task_id="scan_nas_task",
        python_callable=scan_nas,
    )

    extract_and_classify_task = PythonOperator(
        task_id="extract_and_classify_task",
        python_callable=extract_and_classify,
    )

    transform_documents_task = PythonOperator(
        task_id="transform_documents_task",
        python_callable=transform_documents,
    )

    generate_wiki_task = PythonOperator(
        task_id="generate_wiki_task",
        python_callable=generate_wiki_and_metadata,
    )

    fetch_credentials_task >> scan_nas_task >> extract_and_classify_task >> transform_documents_task >> generate_wiki_task
