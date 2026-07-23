from pydantic import BaseModel, DirectoryPath
from typing import List


class NASConfig(BaseModel):
    nas_dir_path: DirectoryPath
    allowed_extensions: List[str] = [".pdf"]
    stability_delay_seconds: float = 1.0
    stability_retries: int = 5
