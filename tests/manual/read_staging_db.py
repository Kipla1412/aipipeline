"""Read-only viewer for the fhir-staging PostgreSQL database.

Purpose:
    Prints the staging_record table (and optionally the observations of one
    record) directly from PostgreSQL — the same DB the fhir-staging API
    serves. Read-only: never writes, updates, or deletes.

Usage:
    python3 tests/manual/read_staging_db.py
    python3 tests/manual/read_staging_db.py <record_id>     # + observations
    python3 tests/manual/read_staging_db.py --status pending # filter

Credentials come from .env (POSTGRES_HOST/PORT/USER/PASSWORD/DB).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(_PROJECT_ROOT / ".env")


def _engine():
    """
    Purpose:
        Builds a SQLAlchemy engine from POSTGRES_* env vars.

    Returns:
        Engine: PostgreSQL engine (fhir-staging database).
    """
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    database = os.getenv("POSTGRES_DB", "fhir-staging")
    return create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    )


def show_records(status: str | None = None) -> None:
    """
    Purpose:
        Prints all staging records (optionally filtered by status).

    Args:
        status: Optional status filter (pending/processing/completed/failed).
    """
    sql = """
        SELECT id, file_id, attachment_title, status,
               updated_by, processed_at, error_message
        FROM staging_record
    """
    params: dict = {}
    if status:
        sql += " WHERE status = :status"
        params["status"] = status
    sql += " ORDER BY id DESC"

    with _engine().connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    print(f"{'id':>6}  {'status':<11}  {'file_id':<38}  title")
    print("-" * 100)
    for r in rows:
        print(f"{r['id']:>6}  {r['status']:<11}  {str(r['file_id']):<38}  {r['attachment_title']}")

    # Status summary
    with _engine().connect() as conn:
        counts = conn.execute(
            text("SELECT status, count(*) AS n FROM staging_record GROUP BY status ORDER BY status")
        ).mappings().all()
    print("-" * 100)
    print("Status counts: " + ", ".join(f"{c['status']}={c['n']}" for c in counts))


def show_record_observations(record_id: int) -> None:
    """
    Purpose:
        Prints the observations attached to one staging record.

    Args:
        record_id: staging_record.id to inspect.
    """
    with _engine().connect() as conn:
        obs = conn.execute(
            text("""
                SELECT o.id, o.code_display, o.value_quantity_value,
                       o.value_quantity_unit, o.value_string, o.status
                FROM observation o
                WHERE o.staging_record_id = :rid
                ORDER BY o.id
            """),
            {"rid": record_id},
        ).mappings().all()

    print(f"\nObservations for staging record {record_id}: {len(obs)}")
    for o in obs:
        value = o["value_quantity_value"] if o["value_quantity_value"] is not None else o["value_string"]
        unit = o["value_quantity_unit"] or ""
        print(f"  [{o['id']}] {o['code_display']:<40} {value} {unit}  ({o['status']})")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    status = None
    if "--status" in sys.argv:
        status = sys.argv[sys.argv.index("--status") + 1]

    show_records(status)

    if args:
        try:
            show_record_observations(int(args[0]))
        except ValueError:
            print(f"\nIgnoring non-numeric record id: {args[0]}")


if __name__ == "__main__":
    main()
