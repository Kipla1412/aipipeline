"""Interactive EMR Pipeline — extract → review → edit → approve → FHIR.

No wiki, no graph. Single interactive session.

Usage:
  python3 run_emr.py "Blood Report - Thomas Reynolds.pdf"
  python3 run_emr.py "CT_small.dcm"
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.components.utils.config import PipelineConfig
from src.components.extractors.pymu_extractor import PyMuPdfExtractor
from src.components.extractors.dicom import DicomExtractor
from src.components.transformers.medical_transformer import MedicalTransformer
from src.components.transformers.medical_classifier import MedicalClassifier
from src.components.emr.staging.service import StagingService
from src.components.emr.review.service import ReviewService
from src.components.emr.fhir.bundle_builder import BundleBuilder
from src.components.emr.repository.fhir_repository import LocalFHIRRepository

settings = PipelineConfig()


def _show(doc: dict, record_id: str):
    """Display the clinical record for review."""
    obs = doc.get("observations", [])
    high_obs = [o for o in obs if o.get("interpretation") in ("high", "abnormal", "critical")]
    normal_obs = [o for o in obs if o.get("interpretation") not in ("high", "abnormal", "critical")]

    print("\n" + "=" * 60)
    print(f"  PATIENT : {doc.get('patient_name')}  ({doc.get('patient_id','N/A')})")
    print(f"  DOCTOR  : {doc.get('doctor_name','N/A')}")
    print(f"  HOSPITAL: {doc.get('hospital','N/A')}")
    print(f"  DATE    : {doc.get('report_date','N/A')}")
    print(f"  TYPE    : {doc.get('report_type','unknown')}")
    print("=" * 60)

    print("\n  DIAGNOSES:")
    for i, d in enumerate(doc.get("diagnoses", [])):
        print(f"    [{i}] {d}")

    print("\n  MEDICATIONS:")
    for i, m in enumerate(doc.get("medications", [])):
        print(f"    [{i}] {m}")

    print(f"\n  OBSERVATIONS: {len(obs)} total, {len(high_obs)} abnormal")
    if high_obs:
        print("  ⚠ ABNORMAL:")
        for o in high_obs[:10]:
            v = o.get("value")
            u = o.get("unit", "")
            r = o.get("reference_range", "?")
            print(f"    {o['display_name']:<25s} {v} {u}  (ref: {r})")

    print(f"\n  SUMMARY: {doc.get('summary','')[:200]}")
    print(f"\n  Record ID: {record_id}")
    print("=" * 60)


def _interactive(staging: StagingService, doc: dict, record_id: str):
    """Edit / approve / reject loop."""
    review = ReviewService(staging)
    field = doc

    while True:
        try:
            cmd = input("\nAction [a]pprove  [r]eject  edit:(dx|med|obs|patient|doctor|hospital|summary) > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting — record saved as draft.")
            return

        if not cmd:
            continue

        parts = cmd.split(maxsplit=3)
        action = parts[0].lower()

        if action in ("a", "approve"):
            staging.start_review(record_id)
            staging.approve(record_id, "reviewer")
            print("✓ APPROVED. Generating FHIR...")

            draft = staging.get(record_id)
            bundle = BundleBuilder().build(draft.reviewed_output)
            repo = LocalFHIRRepository()
            path = repo.save(bundle, record_id)
            print(f"✓ FHIR: {len(bundle.entry)} resources → {path}")
            return

        elif action in ("r", "reject"):
            staging.reject(record_id)
            print("✗ REJECTED")
            return

        elif action in ("q", "quit"):
            print("Saved as draft.")
            return

        elif action in ("dx", "diagnosis", "diagnoses"):
            if len(parts) < 3:
                print("  Usage: dx <index> <new_value>")
                continue
            try:
                idx = int(parts[1])
                new_val = " ".join(parts[2:]) if len(parts) > 2 else parts[2]
                review.edit_diagnosis(record_id, idx, new_val)
                field = staging.get(record_id).reviewed_output
                print(f"  ✓ diagnoses[{idx}] = {new_val}")
            except ValueError:
                print("  Index must be a number")

        elif action in ("patient", "patient_name"):
            if len(parts) < 2:
                print("  Usage: patient <new_name>")
                continue
            review.edit_field(record_id, "patient_name", parts[1])
            field = staging.get(record_id).reviewed_output
            print(f"  ✓ patient_name = {parts[1]}")

        elif action in ("doctor", "doctor_name"):
            if len(parts) < 2:
                print("  Usage: doctor <name>")
                continue
            review.edit_field(record_id, "doctor_name", parts[1])
            field = staging.get(record_id).reviewed_output
            print(f"  ✓ doctor_name = {parts[1]}")

        elif action in ("hospital"):
            if len(parts) < 2:
                print("  Usage: hospital <name>")
                continue
            review.edit_field(record_id, "hospital", parts[1])
            field = staging.get(record_id).reviewed_output
            print(f"  ✓ hospital = {parts[1]}")

        elif action in ("summary"):
            if len(parts) < 2:
                print("  Usage: summary <text>")
                continue
            review.edit_field(record_id, "summary", parts[1] + (" " + parts[2] if len(parts) > 2 else ""))
            field = staging.get(record_id).reviewed_output
            print(f"  ✓ summary updated")

        elif action in ("med", "medication", "medications"):
            if len(parts) < 3:
                print("  Usage: med <index> <new_value>")
                continue
            try:
                idx = int(parts[1])
                new_val = " ".join(parts[2:]) if len(parts) > 2 else parts[2]
                review.edit_field(record_id, f"medications.{idx}", new_val)
                field = staging.get(record_id).reviewed_output
                print(f"  ✓ medications[{idx}] = {new_val}")
            except ValueError:
                print("  Index must be a number")

        elif action in ("obs", "observation", "observations"):
            obs = field.get("observations", [])
            if len(parts) >= 2 and parts[1] == "all":
                for i, o in enumerate(obs):
                    interp = o.get("interpretation", "")
                    flag = "⚠" if interp in ("high", "abnormal", "critical") else " "
                    print(f"  {flag}[{i:2d}] {o['display_name']:<25s} {str(o.get('value','?')):<10s} {o.get('unit',''):<8s} ref:{o.get('reference_range','?')}")
            elif len(parts) >= 2:
                # search by name
                match = [o for o in obs if parts[1].lower() in o["display_name"].lower()]
                for i, o in enumerate(match[:15]):
                    print(f"  [{obs.index(o):2d}] {o['display_name']:<25s} {o.get('value')} {o.get('unit','')}")
                if not match:
                    print(f"  No observation matches '{parts[1]}'")

        elif action in ("help", "?", "h"):
            print("\n  Commands:")
            print("  a / approve      — approve record + generate FHIR")
            print("  r / reject       — reject record")
            print("  dx <idx> <val>   — edit diagnosis")
            print("  med <idx> <val>  — edit medication")
            print("  patient <name>   — edit patient name")
            print("  doctor <name>    — edit doctor name")
            print("  hospital <name>  — edit hospital")
            print("  summary <text>   — edit summary")
            print("  obs all          — show all observations")
            print("  obs <name>       — search observations")
            print("  q / quit         — save as draft and exit")
            print("  help             — this message")

        else:
            print(f"  Unknown: '{cmd}'. Type 'help' for commands.")


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Usage: python3 run_emr.py <file.pdf|file.dcm>")
        sys.exit(1)

    fp = Path(args[0])
    if not fp.exists():
        fp = Path(settings.RAW_PDF_DIR) / args[0]
    if not fp.exists():
        print(f"Not found: {args[0]}")
        sys.exit(1)

    suffix = fp.suffix.lower()
    is_dicom = suffix in (".dcm", ".dicom")

    # ── Extract ──
    print(f"Extracting {fp.name}...")
    if is_dicom:
        extractor = DicomExtractor({
            "output_image_dir": str(settings.EXTRACTED_IMAGE_DIR),
            "extract_preview": True,
        })
        extracted = extractor.extract(str(fp))
    else:
        extractor = PyMuPdfExtractor(settings.get_extractor_config())
        extracted = extractor.extract(str(fp))
    print(f"  {len(extracted.markdown)} chars")

    # ── Classify ──
    classifier = MedicalClassifier({"api_key": settings.OPENAI_API_KEY, "model": "gpt-4o-mini"})
    report_type = await classifier.classify(extracted.markdown)
    print(f"  type: {report_type}")

    # ── Transform ──
    transformer = MedicalTransformer(settings.get_transformer_config())
    print("  LLM extracting...")
    doc = await transformer.transform(
        extracted.markdown,
        dicom_metadata=extracted.dicom_metadata if is_dicom else None,
    )
    doc["report_type"] = report_type
    doc["source_file"] = fp.name
    print(f"  {len(doc.get('observations', []))} observations, {len(doc.get('diagnoses', []))} diagnoses")

    # ── Stage ──
    staging = StagingService()
    draft = staging.create_draft(doc, fp.name)

    # ── Show + Review ──
    _show(doc, draft.record_id)
    _interactive(staging, doc, draft.record_id)


if __name__ == "__main__":
    asyncio.run(main())
