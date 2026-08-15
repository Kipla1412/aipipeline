"""
Module: FileNest Asset Consumer DAG (Airflow 3 Orchestration)
Purpose:
    Scheduled by the 'medical_files_asset' Asset.
    Runs whenever the producer downloads files and emits the Asset.

    For each downloaded file in PostgreSQL, this DAG runs:
        storage/temp/{file} → Extract (PyMuPDF for PDF, DICOM parser)
                            → Classify (report type)
                            → Transform (LLM → Clinical Domain Model with observations)
                            → Save Clinical Domain Model JSON

    Later stages (staging, review, FHIR) attach after transform.

    Conceptually:

        medical_files_asset
              ↓
        consumer DAG (this one)
"""

import sys
import asyncio
import json
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

from src.components.connectors.rdbms import RDBMSConnector
from src.components.repository.filenestrepository import FileNestRepository
from src.components.utils.config import PipelineConfig
from src.components.utils.reader import load_yml
from src.components.extractors.pymu_extractor import PyMuPdfExtractor
from src.components.extractors.dicom import DicomExtractor
from src.components.transformers.medical_transformer import MedicalTransformer
from src.components.transformers.medical_classifier import MedicalClassifier

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config" / "config.yml"


def load_config() -> dict:
    return load_yml(CONFIG_PATH)


cfg = load_config()

# Same logical Asset — must match the producer's URI exactly.
medical_files_asset = Asset(
    name=cfg.get("asset", {}).get("name", "medical_files_asset"),
    uri=cfg.get("asset", {}).get("uri", "file:///medical/files/available"),
    group=cfg.get("asset", {}).get("group", "filenest"),
)


def process_one_file(file_record: dict) -> dict:
    """Extract → classify → transform a single downloaded file into a Clinical Domain Model."""
    filepath = Path(file_record["filepath"])
    if not filepath.exists():
        logger.warning("Skipping %s — file missing on disk (%s)", file_record.get("filename"), filepath)
        return {
            "filename": file_record.get("filename"),
            "status": "skipped",
            "reason": "file missing on disk",
        }

    suffix = filepath.suffix.lower()
    is_dicom = suffix in (".dcm", ".dicom")
    is_pdf = suffix == ".pdf"
    is_image = suffix in (".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp")

    if not (is_dicom or is_pdf or is_image):
        logger.warning("Skipping %s — unsupported type '%s' (supported: PDF/DICOM/image)", filepath.name, suffix)
        return {
            "filename": file_record["filename"],
            "status": "skipped",
            "reason": f"unsupported type {suffix}",
        }

    settings = PipelineConfig()

    # 1. Extract (try/except — a corrupt file should skip, not fail the DAG)
    try:
        if is_dicom:
            extractor = DicomExtractor({
                "output_image_dir": str(settings.EXTRACTED_IMAGE_DIR),
                "extract_preview": True,
            })
            extracted = extractor.extract(str(filepath))
        elif is_image:
            from src.components.extractors.image_analyzer import ImageAnalyzer
            image_analyzer = ImageAnalyzer({"api_key": settings.OPENAI_API_KEY})
            description = asyncio.run(image_analyzer.extract([str(filepath)]))
            from src.components.extractors.schemas.extract_result import ExtractResult
            extracted = ExtractResult(markdown=description, images=[str(filepath)])
            logger.info("Image analyzed via GPT-4V — %d chars", len(description))
        else:
            extractor = PyMuPdfExtractor(settings.get_extractor_config())
            extracted = extractor.extract(str(filepath))
    except Exception as exc:
        logger.warning("Skipping %s — extraction failed: %s", filepath.name, exc)
        return {
            "filename": file_record.get("filename"),
            "status": "skipped",
            "reason": f"extraction failed: {exc}",
        }

    logger.info("Extracted %s — %d chars, %d images",
                filepath.name, len(extracted.markdown), len(extracted.images))

    # 2. Classify
    classifier = MedicalClassifier({
        "api_key": settings.OPENAI_API_KEY,
        "model": cfg.get("classification", {}).get("model", "gpt-4o-mini"),
    })
    report_type = asyncio.run(classifier.classify(extracted.markdown))
    logger.info("Classified %s → %s", filepath.name, report_type)

    # 3. Transform (LLM → Clinical Domain Model with observations)
    transformer = MedicalTransformer(settings.get_transformer_config())
    document = asyncio.run(transformer.transform(
        extracted.markdown,
        dicom_metadata=extracted.dicom_metadata if is_dicom else None,
    ))
    document["report_type"] = report_type
    document["source_file"] = file_record["filename"]
    document["filenest_file_id"] = file_record["filenest_file_id"]

    obs_count = len(document.get("observations", []))
    logger.info("Transformed %s — %d observations, %d diagnoses",
                filepath.name, obs_count, len(document.get("diagnoses", [])))

    # 4. Save Clinical Domain Model JSON (absolute path — Airflow CWD differs)
    out_dir = Path(cfg.get("transformation", {}).get("output_dir", str(_AI_PLATFORM / "storage" / "emr" / "transformed")))
    out_dir.mkdir(parents=True, exist_ok=True)
    # Use filenest_file_id to avoid collisions from duplicate filenames (e.g. multiple check.pdf)
    file_id_short = file_record.get("filenest_file_id", "unknown")[:8]
    out_path = out_dir / f"{Path(file_record['filename']).stem}_{file_id_short}.json"
    out_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info("Saved Clinical Domain Model → %s", out_path)

    return {
        "filename": file_record["filename"],
        "status": "processed",
        "report_type": report_type,
        "observations": obs_count,
        "diagnoses": len(document.get("diagnoses", [])),
        "output": str(out_path),
    }


def medical_processing(**kwargs) -> list:
    """Process every downloaded file from PostgreSQL through extract → transform."""
    logger.info("Medical file asset triggered — consumer DAG running.")

    config = PipelineConfig().get_postgres_config()
    connector = RDBMSConnector(config)
    repo = FileNestRepository(connector)
    try:
        downloaded = [r for r in repo.list_all() if r.download_status == "downloaded"]
        logger.info("PostgreSQL has %d downloaded file(s)", len(downloaded))

        results = []
        for rec in downloaded:
            logger.info("Processing: %s", rec.filename)
            result = process_one_file(rec.model_dump())
            results.append(result)

        return results
    finally:
        repo.close()


with DAG(
    "filenest_asset_consumer",
    default_args={"owner": "alpha_team",
                  "retries": cfg.get("pipeline", {}).get("retries", 1),
                  "retry_delay": timedelta(minutes=cfg.get("pipeline", {}).get("retry_delay_minutes", 5))},
    start_date=datetime(2026, 1, 1),
    schedule=[medical_files_asset],
    catchup=False,
    description="Consumer — extract/classify/transform downloaded medical files",
    tags=["filenest", "asset", "consumer", "medical"],
) as dag:

    processing_task = PythonOperator(
        task_id="medical_extract_transform_task",
        python_callable=medical_processing,
    )
