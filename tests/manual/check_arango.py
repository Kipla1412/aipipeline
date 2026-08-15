"""Verify ArangoDB connection and inspect stored graph data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.components.utils.config import PipelineConfig

settings = PipelineConfig()

print(f"ArangoDB enabled: {settings.arango_enabled}")
print(f"Host: {settings.ARANGO_HOST}:{settings.ARANGO_PORT}")
print(f"Database: {settings.ARANGO_DATABASE}")
print()

if not settings.arango_enabled:
    print("NOT CONFIGURED — set ARANGO_HOST/USERNAME/PASSWORD in .env")
    sys.exit(1)

try:
    from src.components.connectors.arango import ArangoDBConnector

    connector = ArangoDBConnector(settings.get_arango_config())
    db = connector()

    print("Connected to ArangoDB")
    print()

    collections = ["patients", "doctors", "hospitals", "diseases", "medications", "procedures", "edges"]
    total_nodes = 0
    total_edges = 0

    for col_name in collections:
        if db.has_collection(col_name):
            col = db.collection(col_name)
            count = col.count()
            col_type = "edge" if col_name == "edges" else "doc"
            print(f"  {col_name:<18} {count:>5} {col_type}(s)")
            if col_name != "edges":
                total_nodes += count
            else:
                total_edges += count
        else:
            print(f"  {col_name:<18}   (not created yet)")

    print()
    print(f"Total: {total_nodes} nodes, {total_edges} edges")

    if total_nodes > 0:
        print()
        print("Sample patients:")
        for doc in db.collection("patients"):
            print(f"  [{doc['id'][:12]}...] {doc['label']}")
            break

    connector.close()

except ImportError:
    print("python-arango not installed. Run: pip3 install python-arango --break-system-packages")
except Exception as e:
    print(f"Connection failed: {e}")
    print()
    if "401" in str(e):
        print("Check ARANGO_USERNAME and ARANGO_PASSWORD in .env")
    elif "resolve" in str(e).lower():
        print("Check ARANGO_HOST in .env")
