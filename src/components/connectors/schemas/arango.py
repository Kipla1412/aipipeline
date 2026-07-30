"""ArangoDB connection configuration — follows existing connector schema pattern."""

from pydantic import BaseModel, ConfigDict


class ArangoDBConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    host: str
    port: int = 8529
    username: str
    password: str
    database: str
    verify_certs: bool = True
    ca_certs: str | None = None
