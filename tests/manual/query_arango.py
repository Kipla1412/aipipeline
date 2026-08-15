"""Retrieve and query data from ArangoDB graph."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from arango import ArangoClient


def connect():
    from src.components.utils.config import PipelineConfig
    s = PipelineConfig()
    cfg = s.get_arango_config()
    host = cfg["host"].replace("https://", "").replace("http://", "").split(":")[0]
    url = f"https://{host}:{cfg['port']}"
    client = ArangoClient(hosts=url)
    return client.db(cfg["database"], username=cfg["username"], password=cfg["password"], verify=True)


db = connect()

# --- 1. Counts ---
print("=" * 50)
print("COLLECTION COUNTS")
for col_name in ["patients", "doctors", "hospitals", "diseases", "medications", "procedures", "edges"]:
    if db.has_collection(col_name):
        print(f"  {col_name:<18} {db.collection(col_name).count()}")

# --- 2. All patients with their diseases ---
print("\n" + "=" * 50)
print("PATIENTS → DISEASES")
if db.has_collection("patients") and db.has_collection("edges"):
    for patient in db.collection("patients"):
        aql = """
            WITH patients, diseases, edges
            FOR v, e IN 1..1 OUTBOUND @patient_id edges
            FILTER e.relation == 'has_disease'
            RETURN v.label
        """
        result = db.aql.execute(aql, bind_vars={"patient_id": patient["_id"]})
        diseases = list(result)
        print(f"  {patient['label']}: {diseases}")

# --- 3. All patients with their doctors ---
print("\n" + "=" * 50)
print("PATIENTS → DOCTORS")
if db.has_collection("patients"):
    for patient in db.collection("patients"):
        aql = """
            WITH patients, doctors, edges
            FOR v, e IN 1..1 OUTBOUND @patient_id edges
            FILTER e.relation == 'treated_by'
            RETURN v.label
        """
        result = db.aql.execute(aql, bind_vars={"patient_id": patient["_id"]})
        doctors = list(result)
        print(f"  {patient['label']} → treated by {doctors}")

# --- 4. Full patient summary with AQL graph traversal ---
print("\n" + "=" * 50)
print("FULL PATIENT SUMMARY (graph traversal)")
if db.has_collection("patients"):
    for patient in db.collection("patients"):
        print(f"\n  {patient['label']}")
        for rel, label, with_col in [
            ("has_disease", "Diseases", "diseases"),
            ("has_medication", "Medications", "medications"),
            ("treated_by", "Doctor", "doctors"),
            ("admitted_at", "Hospital", "hospitals"),
        ]:
            aql = f"""
                WITH patients, {with_col}, edges
                FOR v, e IN 1..1 OUTBOUND @pid edges
                FILTER e.relation == '{rel}'
                RETURN v.label
            """
            result = db.aql.execute(aql, bind_vars={"pid": patient["_id"]})
            items = list(result)
            if items:
                print(f"    {label}: {', '.join(items)}")

# --- 5. Count diseases across all patients ---
print("\n" + "=" * 50)
print("DISEASE FREQUENCY")
aql = """
    WITH edges
    FOR edge IN edges
    FILTER edge.relation == 'has_disease'
    COLLECT disease_key = edge._to WITH COUNT INTO count
    SORT count DESC
    LET disease = DOCUMENT(disease_key)
    RETURN {disease: disease.label, count: count}
"""
for d in db.aql.execute(aql):
    print(f"  {d['disease']}: {d['count']} patient(s)")
