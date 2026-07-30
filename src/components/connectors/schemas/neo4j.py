"""Neo4j connection configuration — follows existing connector schema pattern."""

from pydantic import BaseModel, ConfigDict


class Neo4jConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    uri: str
    username: str
    password: str
    database: str = "neo4j"
    verify_certs: bool = True
