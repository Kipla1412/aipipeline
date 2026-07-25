import os
from pathlib import Path
from typing import List
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PipelineConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MED_WIKI_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENV: str = Field("development")
    LOG_LEVEL: str = Field("INFO")
    OPENAI_API_KEY: str = Field("")
    OPENAI_BASE_URL: str | None = Field(None)
    LLM_MODEL_NAME: str = Field("gpt-4o-mini")
    BASE_STORAGE_DIR: Path = Field(Path("storage"))
    RAW_PDF_DIR: Path = Field(Path("storage/raw"))
    EXTRACTED_IMAGE_DIR: Path = Field(Path("storage/images"))
    WIKI_OUTPUT_DIR: Path = Field(Path("storage/wiki"))
    METADATA_INDEX_PATH: Path = Field(Path("storage/metadata/index.json"))
    METADATA_REPO_BACKEND: str = Field("json")
    NAS_ALLOWED_EXTENSIONS: List[str] = Field([".pdf", ".dcm"])
    NAS_STABILITY_DELAY: float = Field(1.0)
    NAS_STABILITY_RETRIES: int = Field(5)

    @model_validator(mode="after")
    def _fallback_api_key(self):
        if not self.OPENAI_API_KEY:
            from_env = os.getenv("OPENAI_API_KEY", "")
            if from_env:
                object.__setattr__(self, "OPENAI_API_KEY", from_env)
        return self

    def initialize_system_directories(self):
        for d in [self.BASE_STORAGE_DIR, self.RAW_PDF_DIR, self.EXTRACTED_IMAGE_DIR, self.WIKI_OUTPUT_DIR, self.METADATA_INDEX_PATH.parent]:
            d.mkdir(parents=True, exist_ok=True)

    def get_connector_config(self) -> dict:
        return {"nas_dir_path": str(self.RAW_PDF_DIR), "allowed_extensions": self.NAS_ALLOWED_EXTENSIONS, "stability_delay_seconds": self.NAS_STABILITY_DELAY, "stability_retries": self.NAS_STABILITY_RETRIES}

    def get_extractor_config(self) -> dict:
        return {"extract_images": True, "output_image_dir": str(self.EXTRACTED_IMAGE_DIR)}

    def get_transformer_config(self) -> dict:
        return {"model_name": self.LLM_MODEL_NAME, "api_key": self.OPENAI_API_KEY, "base_url": self.OPENAI_BASE_URL}

    def get_wiki_generator_config(self) -> dict:
        return {"base_wiki_dir": str(self.WIKI_OUTPUT_DIR)}

    def get_metadata_config(self) -> dict:
        return {"backend": self.METADATA_REPO_BACKEND, "index_path": str(self.METADATA_INDEX_PATH)}
