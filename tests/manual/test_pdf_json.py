"""Process a real medical PDF/DICOM through the full pipeline and dump JSON.

Usage:
  python3 test_pdf_json.py "Blood Report - Thomas Reynolds.pdf"
  python3 test_pdf_json.py "Chest X-Ray - Robert Chen.pdf"
  python3 test_pdf_json.py "CT_small.dcm"
  python3 test_pdf_json.py                          # default blood report
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.components.utils.config import PipelineConfig
from src.components.extractors.pymu_extractor import PyMuPdfExtractor
from src.components.extractors.dicom import DicomExtractor
from src.components.transformers.medical_transformer import MedicalTransformer
from src.components.transformers.medical_classifier import MedicalClassifier

settings = PipelineConfig()


async def process_file(filepath: Path) -> dict:
    suffix = filepath.suffix.lower()
    is_dicom = suffix in (".dcm", ".dicom")

    # Extract
    print(f"Extracting {filepath.name}...")
    if is_dicom:
        extractor = DicomExtractor({
            "output_image_dir": str(settings.EXTRACTED_IMAGE_DIR),
            "extract_preview": True,
        })
        extracted = extractor.extract(str(filepath))
    else:
        extractor = PyMuPdfExtractor(settings.get_extractor_config())
        extracted = extractor.extract(str(filepath))

    print(f"  {len(extracted.markdown)} chars extracted")

    # Classify
    classifier = MedicalClassifier({"api_key": settings.OPENAI_API_KEY, "model": "gpt-4o-mini"})
    report_type = await classifier.classify(extracted.markdown)
    print(f"  Classified: {report_type}")

    # Transform (LLM call)
    transformer = MedicalTransformer(settings.get_transformer_config())
    print(f"  Sending to LLM...")
    document = await transformer.transform(
        extracted.markdown,
        dicom_metadata=extracted.dicom_metadata if is_dicom else None,
    )
    print(f"  Done — {len(document.get('observations', []))} observations, "
          f"{len(document.get('diagnoses', []))} diagnoses\n")

    return document


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if args:
        filepath = Path(args[0])
        if not filepath.exists():
            filepath = Path(settings.RAW_PDF_DIR) / args[0]
    else:
        filepath = Path(settings.RAW_PDF_DIR) / "Blood Report - Thomas Reynolds.pdf"

    if not filepath.exists():
        print(f"File not found: {filepath}")
        print("Usage: python3 test_pdf_json.py <filename.pdf|filename.dcm>")
        sys.exit(1)

    document = await process_file(filepath)

    print("=" * 70)
    print(f"  FULL JSON OUTPUT — {filepath.name}")
    print("=" * 70)
    print(json.dumps(document, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(main())
