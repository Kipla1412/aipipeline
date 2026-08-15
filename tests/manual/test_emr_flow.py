"""Real EMR transformer-layer test — processes actual PDF/DICOM files.

Runs ONLY the pre-staging pipeline (no staging, no review, no FHIR):
  Extract → Classify → Transform (LLM)

Shows the real Clinical Domain Model output that would feed the staging area.

Usage:
  python3 test_emr_flow.py "Blood Report - Thomas Reynolds.pdf"
  python3 test_emr_flow.py "CT_small.dcm"
  python3 test_emr_flow.py --all              # first PDF + first DICOM
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


def separator(title: str) -> None:
    print(f"\n{'═' * 70}")
    print(f"  {title}")
    print(f"{'═' * 70}")


async def run_flow(filepath: Path) -> dict:
    suffix = filepath.suffix.lower()
    is_dicom = suffix in (".dcm", ".dicom")

    # ── 1. EXTRACT ──
    separator(f"STEP 1 — EXTRACT: {filepath.name}")
    if is_dicom:
        extractor = DicomExtractor({
            "output_image_dir": str(settings.EXTRACTED_IMAGE_DIR),
            "extract_preview": True,
        })
        extracted = extractor.extract(str(filepath))
    else:
        extractor = PyMuPdfExtractor(settings.get_extractor_config())
        extracted = extractor.extract(str(filepath))

    print(f"  ✓ {len(extracted.markdown)} chars, {len(extracted.images)} images")
    if is_dicom and extracted.dicom_metadata:
        meta = extracted.dicom_metadata
        print(f"  ✓ DICOM: modality={meta.get('modality')}, "
              f"manufacturer={meta.get('manufacturer')}")

    # ── 2. CLASSIFY ──
    separator("STEP 2 — CLASSIFY")
    classifier = MedicalClassifier({"api_key": settings.OPENAI_API_KEY, "model": "gpt-4o-mini"})
    report_type = await classifier.classify(extracted.markdown)
    print(f"  ✓ report_type = {report_type}")

    # ── 3. TRANSFORM (LLM) ──
    separator("STEP 3 — TRANSFORM (LLM)")
    transformer = MedicalTransformer(settings.get_transformer_config())
    doc = await transformer.transform(
        extracted.markdown,
        dicom_metadata=extracted.dicom_metadata if is_dicom else None,
    )
    doc["report_type"] = report_type
    doc["source_file"] = filepath.name

    print(f"  ✓ patient: {doc.get('patient_name')} ({doc.get('patient_id', 'N/A')})")
    print(f"  ✓ doctor:  {doc.get('doctor_name', 'N/A')}")
    print(f"  ✓ hospital: {doc.get('hospital', 'N/A')}")
    print(f"  ✓ date:    {doc.get('report_date', 'N/A')}")

    print(f"\n  DIAGNOSES ({len(doc.get('diagnoses', []))}):")
    for d in doc.get("diagnoses", []):
        print(f"    - {d}")

    print(f"\n  MEDICATIONS ({len(doc.get('medications', []))}):")
    for m in doc.get("medications", []):
        print(f"    - {m}")

    obs = doc.get("observations", [])
    abnormal = [o for o in obs if o.get("interpretation") in ("high", "abnormal", "critical")]
    print(f"\n  OBSERVATIONS ({len(obs)} total, {len(abnormal)} abnormal):")
    for o in abnormal[:8]:
        print(f"    ⚠ {o['display_name']} = {o.get('value')} {o.get('unit', '')} "
              f"(ref: {o.get('reference_range', '?')})")

    print(f"\n  SUMMARY:")
    print(f"    {doc.get('summary', '')[:250]}")

    # Imaging
    if doc.get("imaging"):
        print(f"\n  IMAGING:")
        for k, v in doc.get("imaging", {}).items():
            if v is not None:
                print(f"    {k}: {v}")

    # ── FULL JSON OUTPUT ──
    separator("FULL JSON OUTPUT (Clinical Domain Model)")
    print(json.dumps(doc, indent=2, ensure_ascii=False, default=str))

    # Also save to a file
    output_dir = Path("storage/emr/transformed")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{filepath.stem}.json"
    json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n  ✓ JSON saved → {json_path}")

    separator("RESULT — READY FOR STAGING")
    print(f"  ✓ record ready: patient='{doc.get('patient_name')}', "
          f"{len(doc.get('observations', []))} obs, {len(doc.get('diagnoses', []))} dx")
    print(f"  ✓ Next step would be: StagingService().create_draft(doc, '{filepath.name}')")

    return doc


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    test_all = "--all" in sys.argv

    if test_all:
        pdfs = sorted(Path(settings.RAW_PDF_DIR).glob("*.pdf"))
        dcms = sorted(Path(settings.RAW_PDF_DIR).glob("*.dcm"))
        files = [f for f in (pdfs[:1] + dcms[:1]) if f.exists()]
    elif args:
        files = []
        for a in args:
            p = Path(a)
            if not p.exists():
                p = Path(settings.RAW_PDF_DIR) / a
            if p.exists():
                files.append(p)
            else:
                print(f"SKIPPED {a} — not found")
    else:
        default = Path(settings.RAW_PDF_DIR) / "Blood Report - Thomas Reynolds.pdf"
        files = [default] if default.exists() else []

    if not files:
        print(f"No files found in {settings.RAW_PDF_DIR}")
        print("Usage: python3 test_emr_flow.py <file.pdf|file.dcm> [--all]")
        sys.exit(1)

    print(f"Testing {len(files)} file(s):")
    for f in files:
        print(f"  {f}")

    for f in files:
        try:
            await run_flow(f)
        except Exception as e:
            print(f"\n✗ FAILED for {f.name}: {e}")
            import traceback
            traceback.print_exc()

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
