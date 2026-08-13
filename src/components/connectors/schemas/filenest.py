"""FileNest connection configuration — follows existing connector schema pattern."""

from pydantic import BaseModel, ConfigDict


class FileNestConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=(), extra="ignore")

    api_key: str
    project_id: str
    base_url: str
    timeout: int = 60
