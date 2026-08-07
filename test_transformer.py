"""End-to-end test for the Medical Transformer Clinical Domain Model.

Processes real PDF and DICOM files through the transformer and shows:
  1. Raw extracted text
  2. Structured LLM output (rich domain models)
  3. Flattened consumer output (backward compat)
  4. Consumer compatibility checks

Usage:
  python3 test_transformer.py                            # test default PDF
  python3 test_transformer.py <file.pdf>                 # test specific PDF
  python3 test_transformer.py <file.dcm>                 # test specific DICOM
  python3 test_transformer.py --all                      # test first PDF + first DICOM
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


def print_separator(title: str) -> None:
    print(f"\n{'═' * 70}")
    print(f"  {title}")
    print(f"{'═' * 70}")


def print_dict_section(data: dict, key: str, label: str) -> None:
    values = data.get(key)
    if not values:
        print(f"  {label}: (empty)")
        return
    print(f"  {label}:")
    if isinstance(values, list):
        for item in values:
            if isinstance(item, dict):
                for k, v in item.items():
                    print(f"      {k}: {v!r}")
                print()
            else:
                print(f"    - {item}")


async def test_file(filepath: Path) -> dict:
    print_separator(f"Testing: {filepath.name}")

    suffix = filepath.suffix.lower()
    is_dicom = suffix in (".dcm", ".dicom")

    # ---- EXTRACT ----
    print("\n── EXTRACT ──")
    if is_dicom:
        extractor = DicomExtractor({
            "output_image_dir": str(settings.EXTRACTED_IMAGE_DIR),
            "extract_preview": True,
        })
        extracted = extractor.extract(str(filepath))
    else:
        extractor = PyMuPdfExtractor(settings.get_extractor_config())
        extracted = extractor.extract(str(filepath))

    print(f"  {len(extracted.markdown)} chars, {len(extracted.images)} images")
    if extracted.markdown:
        preview = extracted.markdown[:300].replace("\n", " ").replace("\r", "")
        print(f"  Text preview: {preview}...")

    # ---- CLASSIFY ----
    if settings.OPENAI_API_KEY:
        classifier = MedicalClassifier({"api_key": settings.OPENAI_API_KEY, "model": "gpt-4o-mini"})
        report_type = await classifier.classify(extracted.markdown)
    else:
        report_type = "unknown"
    print(f"  Classified: {report_type}")

    # ---- TRANSFORM ----
    print("\n── TRANSFORM (LLM) ──")

    if not settings.OPENAI_API_KEY:
        print("  SKIPPED — no OPENAI_API_KEY set")
        return {}

    transformer = MedicalTransformer(settings.get_transformer_config())

    full_text = extracted.markdown

    print(f"  Sending {len(full_text)} chars to LLM...")

    try:
        document = await transformer.transform(
            full_text, dicom_metadata=extracted.dicom_metadata if is_dicom else None
        )
    except Exception as e:
        print(f"  TRANSFORM FAILED: {e}")
        return {}

    # ---- SHOW STRUCTURED OUTPUT ----
    print_separator("STRUCTURED OUTPUT (what consumers see — flat dict)")

    print(f"  patient_name:       {document.get('patient_name')!r}")
    print(f"  patient_id:         {document.get('patient_id')!r}")
    print(f"  doctor_name:        {document.get('doctor_name')!r}")
    print(f"  hospital:           {document.get('hospital')!r}")
    print(f"  report_date:        {document.get('report_date')!r}")

    print_dict_section(document, "diagnoses", "DIAGNOSES")
    print_dict_section(document, "medications", "MEDICATIONS")
    print_dict_section(document, "procedures", "PROCEDURES")

    print("\n  SUMMARY:")
    summary = document.get("summary", "")
    print(f"    {summary}")

    # Observations
    observations = document.get("observations", [])
    if observations:
        print("\n  OBSERVATIONS:")
        for o in observations:
            if isinstance(o, dict):
                name = o.get('display_name') or o.get('name', '?')
                value = o.get('value', '?')
                unit = o.get('unit') or ''
                print(f"    [{o.get('category', '?')}] {name} = {value} {unit}")
                if o.get("reference_range"):
                    print(f"      reference_range: {o['reference_range']}")
                if o.get("interpretation"):
                    print(f"      interpretation: {o['interpretation']}")
                bp = o.get("blood_pressure")
                if bp and isinstance(bp, dict):
                    print(f"      BP: systolic={bp.get('systolic')}, diastolic={bp.get('diastolic')}")
    else:
        print("\n  OBSERVATIONS: (none)")

    # Vitals
    vitals = document.get("vitals")
    if vitals:
        print("\n  VITALS (deprecated):")
        for k, v in vitals.items():
            if v:
                print(f"    {k}: {v}")

    # Imaging
    imaging = document.get("imaging")
    if imaging:
        print("\n  IMAGING STUDY:")
        for k, v in imaging.items():
            if v is not None:
                print(f"    {k}: {v}")

    # Sections
    sections = document.get("sections")
    if sections:
        print(f"\n  SECTIONS: {len(sections)} headings")
        for heading, content in list(sections.items())[:5]:
            print(f"    [{heading}] {content[:80]}...")

    # ---- CONSUMER COMPATIBILITY CHECK ----
    print_separator("CONSUMER COMPATIBILITY CHECK")

    checks = [
        ("patient_name is str", isinstance(document.get("patient_name"), str)),
        ("diagnoses is list[str]", isinstance(document.get("diagnoses"), list) and
         all(isinstance(d, str) for d in document.get("diagnoses", []))),
        ("medications is list[str]", isinstance(document.get("medications"), list) and
         all(isinstance(m, str) for m in document.get("medications", []))),
        ("procedures is list[str]", isinstance(document.get("procedures"), list) and
         all(isinstance(p, str) for p in document.get("procedures", []))),
        ("vitals is dict or None", isinstance(document.get("vitals"), (dict, type(None)))),
        ("summary is str", isinstance(document.get("summary"), str)),
        ("observations present", "observations" in document),
    ]

    all_pass = True
    for check_name, result in checks:
        status = "✓" if result else "✗ FAIL"
        if not result:
            all_pass = False
        print(f"  {status}  {check_name}")

    print(f"\n  {'ALL COMPATIBILITY CHECKS PASSED ✓' if all_pass else 'SOME CHECKS FAILED ✗'}")

    return document


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    test_all = "--all" in sys.argv

    if test_all:
        pdf_files = sorted(Path(settings.RAW_PDF_DIR).glob("*.pdf"))
        files_to_test = [f for f in pdf_files[:1] if f.exists()]
    elif args:
        files_to_test = []
        for a in args:
            p = Path(a)
            if not p.exists():
                p = Path(settings.RAW_PDF_DIR) / a
            if p.exists():
                files_to_test.append(p)
            else:
                print(f"SKIPPED {a} — file not found")
    else:
        default = Path(settings.RAW_PDF_DIR) / "Blood Report - Thomas Reynolds.pdf"
        files_to_test = [default] if default.exists() else []

    if not files_to_test:
        print(f"No files found in {settings.RAW_PDF_DIR}")
        print("Usage: python3 test_transformer.py <file.pdf|file.dcm> [--all]")
        return

    print(f"Files to test: {len(files_to_test)}")
    for f in files_to_test:
        print(f"  {f}")

    for filepath in files_to_test:
        if not filepath.exists():
            print(f"\nSKIPPED {filepath.name} — file not found")
            continue
        await test_file(filepath)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
