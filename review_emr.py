#!/usr/bin/env python3
"""Interactive EMR review — view, edit, approve clinical records.

Usage:
  python3 review_emr.py                    # list all drafts/pending
  python3 review_emr.py <record_id>        # review a specific record
"""

import readline
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.components.emr.staging.service import StagingService
from src.components.emr.review.service import ReviewService
from src.components.emr.fhir.bundle_builder import BundleBuilder
from src.components.emr.repository.fhir_repository import LocalFHIRRepository


def show_record(draft):
    output = draft.reviewed_output
    print("=" * 60)
    print(f"  Record: {draft.record_id}")
    print(f"  File:   {draft.source_file}")
    print(f"  State:  {draft.workflow_state}")
    print(f"  Type:   {draft.report_type or 'unknown'}")
    print("=" * 60)

    print(f"\n  PATIENT: {output.get('patient_name')} ({output.get('patient_id','N/A')})")
    print(f"  DOCTOR:  {output.get('doctor_name','N/A')}")
    print(f"  HOSPITAL:{output.get('hospital','N/A')}")
    print(f"  DATE:    {output.get('report_date','N/A')}")

    print("\n  DIAGNOSES:")
    for i, d in enumerate(output.get("diagnoses", [])):
        print(f"    [{i}] {d}")

    print("\n  MEDICATIONS:")
    for i, m in enumerate(output.get("medications", [])):
        print(f"    [{i}] {m}")

    print("\n  PROCEDURES:")
    for i, p in enumerate(output.get("procedures", [])):
        print(f"    [{i}] {p}")

    obs = output.get("observations", [])
    print(f"\n  OBSERVATIONS: ({len(obs)} total)")
    high_obs = [o for o in obs if o.get("interpretation") in ("high", "abnormal", "critical")]
    if high_obs:
        print("  ⚠ ABNORMAL:")
        for o in high_obs:
            print(f"    [{o['display_name']}] {o['value']} {o.get('unit','')} "
                  f"(ref: {o.get('reference_range','?')} → {o['interpretation']})")
    normal = [o for o in obs if o.get("interpretation") not in ("high", "abnormal", "critical")]
    if normal:
        print(f"\n  Normal: {len(normal)} observations — type 'obs' to see all")

    print(f"\n  SUMMARY: {output.get('summary','')[:200]}")

    print(f"\n  AUDIT: {len(draft.audit_log)} entries (type 'audit' to see)")


def interactive_review(draft):
    staging = StagingService()
    review = ReviewService(staging)
    rid = draft.record_id

    show_record(draft)

    while True:
        try:
            cmd = input("\n  [e]dit [a]pprove [r]eject [o]bs [audit] [?]help > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            return

        if cmd in ("q", "quit", "exit"):
            return

        elif cmd == "?" or cmd == "help":
            print("  edit <field> <value>  — edit a field (e.g., 'edit diagnoses 0 New Dx')")
            print("  obs                   — show all observations")
            print("  approve               — approve and generate FHIR")
            print("  reject                — reject the record")
            print("  audit                 — show audit trail")
            print("  q                     — quit without saving")

        elif cmd == "obs" or cmd == "o":
            obs = draft.reviewed_output.get("observations", [])
            for i, o in enumerate(obs):
                interp = o.get("interpretation", "")
                flag = "⚠" if interp in ("high", "abnormal", "critical") else " "
                print(f"  {flag}[{i:2d}] {o['display_name']:<25s} {str(o.get('value','?')):<10s} "
                      f"{o.get('unit',''):<8s} ref:{o.get('reference_range','?')} → {interp}")

        elif cmd == "audit":
            print("\n  AUDIT TRAIL:")
            for e in draft.audit_log:
                print(f"    {e.timestamp[:19]} | {e.reviewer:<10s} | {e.field:<20s} | "
                      f"{str(e.previous_value)[:30]} → {str(e.new_value)[:30]}")

        elif cmd.startswith("edit ") or cmd == "e":
            parts = cmd.split(None, 3)
            draft = _handle_edit(draft, review, parts)

        elif cmd == "approve" or cmd == "a":
            review.approve(rid, "reviewer")
            print("  ✓ APPROVED. Generating FHIR...")
            draft = staging.get(rid)
            bundle = BundleBuilder().build(draft.reviewed_output)
            repo = LocalFHIRRepository()
            path = repo.save(bundle, rid)
            print(f"  ✓ FHIR Bundle: {len(bundle.entry)} resources → {path}")
            return

        elif cmd == "reject" or cmd == "r":
            review.reject(rid)
            print("  ✗ REJECTED")
            return

        elif cmd:
            print("  Unknown command. Type ? for help.")


def _handle_edit(draft, review, parts):
    rid = draft.record_id
    if len(parts) < 3:
        print("  Usage: edit <field> [index] <new_value>")
        print("  Examples: edit diagnoses 0 New Diagnosis Name")
        print("            edit summary New summary text")
        return draft

    field = parts[1]
    rest = parts[2:] if len(parts) > 2 else []

    if field == "diagnoses" or field == "diagnosis" or field == "dx":
        if len(rest) >= 2:
            try:
                idx = int(rest[0])
                new_val = rest[1]
                return review.edit_diagnosis(rid, idx, new_val)
            except ValueError:
                print("  Usage: edit diagnosis <index> <new_name>")
        else:
            print("  Usage: edit diagnosis <index> <new_name>")
    elif field == "summary":
        review.edit_field(rid, "summary", " ".join(rest))
        return staging.get(rid)
    elif field in ("patient_name", "doctor_name", "hospital", "report_date"):
        review.edit_field(rid, field, " ".join(rest))
        return staging.get(rid)
    else:
        print(f"  Unknown field: {field}")
    return draft


def list_pending():
    staging = StagingService()
    pending = staging.get_pending()
    drafts = staging.list_all()
    drafts_only = [d for d in drafts if d.workflow_state == "draft"]

    print(f"\n  DRAFT: {len(drafts_only)} | PENDING: {len(pending)} | ALL: {len(drafts)}")
    for d in drafts:
        output = d.reviewed_output or d.ai_output or {}
        patient = output.get("patient_name", "?")
        file_ = d.source_file or "?"
        obs_count = len(output.get("observations", []))
        dx_count = len(output.get("diagnoses", []))
        state_icon = {"draft": "◻", "pending_review": "○", "in_review": "⟳",
                       "needs_correction": "✎", "approved": "✓", "rejected": "✗"}.get(d.workflow_state, "?")
        print(f"  {state_icon} {d.record_id} | {patient:<25s} | {d.workflow_state:<18s} | {obs_count} obs, {dx_count} dx | {file_}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        list_pending()
        print("\nUsage: python3 review_emr.py <record_id>  — to review a specific record")
    else:
        staging = StagingService()
        draft = staging.get(args[0])
        if draft is None:
            print(f"Record not found: {args[0]}")
            list_pending()
        else:
            interactive_review(draft)
