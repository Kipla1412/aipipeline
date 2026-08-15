"""Verify Neo4j connection and inspect stored graph data."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.components.utils.config import PipelineConfig

settings = PipelineConfig()
print(f"Neo4j enabled: {settings.neo4j_enabled}")
print(f"URI: {settings.NEO4J_URI}")
print(f"Database: {settings.NEO4J_DATABASE}")
print()

if not settings.neo4j_enabled:
    print("NOT CONFIGURED")
    sys.exit(1)

from src.components.connectors.neo4j import Neo4jConnector

connector = Neo4jConnector(settings.get_neo4j_config())
driver = connector()

with driver.session(database=settings.NEO4J_DATABASE) as session:
    result = session.run("MATCH (n) RETURN labels(n) AS labels, count(n) AS cnt")
    print("Node counts:")
    for record in result:
        print(f"  {record['labels']}: {record['cnt']}")

    result = session.run("MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS cnt")
    print("\nRelationship counts:")
    for record in result:
        print(f"  {record['rel']}: {record['cnt']}")

connector.close()
print("\nDone.")
