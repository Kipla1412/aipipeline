import os
import logging
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Load bare (non-prefixed) env vars (e.g. POSTGRES_HOST) into os.environ.
_PROJECT_ROOT = Path(__file__).resolve()
for _ in range(4):
    _PROJECT_ROOT = _PROJECT_ROOT.parent
load_dotenv(_PROJECT_ROOT / ".env")


class PipelineConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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
    ARANGO_HOST: str = Field("")
    ARANGO_PORT: int = Field(8529)
    ARANGO_USERNAME: str = Field("")
    ARANGO_PASSWORD: str = Field("")
    ARANGO_DATABASE: str = Field("medical_graph")
    ARANGO_VERIFY_CERTS: bool = Field(True)
    NEO4J_URI: str = Field("")
    NEO4J_USERNAME: str = Field("")
    NEO4J_PASSWORD: str = Field("")
    NEO4J_DATABASE: str = Field("neo4j")
    POSTGRES_HOST: str = Field("")
    POSTGRES_PORT: int = Field(5432)
    POSTGRES_USER: str = Field("")
    POSTGRES_PASSWORD: str = Field("")
    POSTGRES_DB: str = Field("structured_data_pipeline")
    FHIR_STAGING_BASE_URL: str = Field("http://localhost:8002")
    FHIR_STAGING_SUMMARY_FIELD: str = Field(
        "summary",
        description="fhir-staging ObservationInput field that carries the per-observation AI summary",
    )

    # ── Clinical Document Embedding / Indexing (document chat) ─────────────
    EMBEDDING_PROVIDER: str = Field("jina")
    JINA_MODEL: str = Field("jina-embeddings-v3")
    JINA_DIMENSIONS: int = Field(1024)
    JINA_TASK_PASSAGE: str = Field("retrieval.passage")
    JINA_TASK_QUERY: str = Field("retrieval.query")
    JINA_BATCH_SIZE: int = Field(50)
    INDEXING_BATCH_SIZE: int = Field(50)
    CHUNK_MAX_CHARS: int = Field(1500)
    CHUNK_OVERLAP_CHARS: int = Field(150)
    JINA_BASE_URL: str = Field("https://api.jina.ai/v1/")
    JINA_API_KEY: str = Field("")
    JINA_TIMEOUT: int = Field(60)
    JINA_MAX_RETRIES: int = Field(5)
    JINA_BASE_BACKOFF: float = Field(1.0)
    OPENSEARCH_HOST: str = Field("")
    OPENSEARCH_PORT: int = Field(9200)
    OPENSEARCH_SCHEMA: str = Field("http")
    OPENSEARCH_LOGIN: str = Field("")
    OPENSEARCH_PASSWORD: str = Field("")
    OPENSEARCH_VERIFY_CERTS: bool = Field(False)
    OPENSEARCH_CA_CERTS: str | None = Field(None)
    OPENSEARCH_INDEX_NAME: str = Field("clinical_documents")

    @model_validator(mode="after")
    def _fallback_api_key(self):
        """
        Purpose:
            Reads OPENAI_API_KEY from the environment if not set in .env.

        Returns:
            PipelineConfig: Self with potentially populated API key.
        """
        if not self.OPENAI_API_KEY:
            from_env = os.getenv("OPENAI_API_KEY", "")
            if from_env:
                object.__setattr__(self, "OPENAI_API_KEY", from_env)
        return self

    def initialize_system_directories(self):
        """
        Purpose:
            Creates all storage directories (raw, images, wiki, metadata) if missing.
        """
        for d in [self.BASE_STORAGE_DIR, self.RAW_PDF_DIR, self.EXTRACTED_IMAGE_DIR, self.WIKI_OUTPUT_DIR, self.METADATA_INDEX_PATH.parent]:
            d.mkdir(parents=True, exist_ok=True)

    def get_connector_config(self) -> dict:
        """
        Purpose:
            Packages NAS connector settings into a config dict.

        Returns:
            dict: nas_dir_path, allowed_extensions, stability_delay_seconds, stability_retries.
        """
        return {"nas_dir_path": str(self.RAW_PDF_DIR), "allowed_extensions": self.NAS_ALLOWED_EXTENSIONS, "stability_delay_seconds": self.NAS_STABILITY_DELAY, "stability_retries": self.NAS_STABILITY_RETRIES}

    def get_extractor_config(self) -> dict:
        """
        Purpose:
            Packages extractor settings into a config dict.

        Returns:
            dict: extract_images, output_image_dir.
        """
        return {"extract_images": True, "output_image_dir": str(self.EXTRACTED_IMAGE_DIR)}

    def get_transformer_config(self) -> dict:
        """
        Purpose:
            Packages LLM transformer settings into a config dict.

        Returns:
            dict: model_name, api_key, base_url.
        """
        return {"model_name": self.LLM_MODEL_NAME, "api_key": self.OPENAI_API_KEY, "base_url": self.OPENAI_BASE_URL}

    def get_wiki_generator_config(self) -> dict:
        """
        Purpose:
            Packages wiki generator settings into a config dict.

        Returns:
            dict: base_wiki_dir.
        """
        return {"base_wiki_dir": str(self.WIKI_OUTPUT_DIR)}

    def get_metadata_config(self) -> dict:
        """
        Purpose:
            Packages metadata repository settings into a config dict.

        Returns:
            dict: backend, index_path.
        """
        return {"backend": self.METADATA_REPO_BACKEND, "index_path": str(self.METADATA_INDEX_PATH)}

    def get_arango_config(self) -> dict:
        """
        Purpose:
            Packages ArangoDB connection settings into a config dict.

        Returns:
            dict: host, port, username, password, database, verify_certs.
        """
        return {
            "host": self.ARANGO_HOST,
            "port": self.ARANGO_PORT,
            "username": self.ARANGO_USERNAME,
            "password": self.ARANGO_PASSWORD,
            "database": self.ARANGO_DATABASE,
            "verify_certs": self.ARANGO_VERIFY_CERTS,
        }

    @property
    def arango_enabled(self) -> bool:
        """
        Purpose:
            Determines whether ArangoDB is fully configured.

        Returns:
            bool: True when host, username, and password are set.
        """
        return bool(self.ARANGO_HOST and self.ARANGO_USERNAME and self.ARANGO_PASSWORD)

    def get_neo4j_config(self) -> dict:
        """
        Purpose:
            Packages Neo4j connection settings into a config dict.

        Returns:
            dict: uri, username, password, database.
        """
        return {
            "uri": self.NEO4J_URI,
            "username": self.NEO4J_USERNAME,
            "password": self.NEO4J_PASSWORD,
            "database": self.NEO4J_DATABASE,
        }

    @property
    def neo4j_enabled(self) -> bool:
        """
        Purpose:
            Determines whether Neo4j is fully configured.

        Returns:
            bool: True when uri, username, and password are set.
        """
        return bool(self.NEO4J_URI and self.NEO4J_USERNAME and self.NEO4J_PASSWORD)

    def get_postgres_config(self) -> dict:
        """
        Purpose:
            Packages PostgreSQL connection settings into a config dict.

        Returns:
            dict: type, host, port, database, login, password — ready for
                  RDBMSConnector / sqlalchemy URL generation.

        Raises:
            ValueError: If host, user, or password is not configured.
        """
        if not self.postgres_enabled:
            raise ValueError(
                "PostgreSQL not configured — set POSTGRES_HOST, "
                "POSTGRES_USER, POSTGRES_PASSWORD in .env"
            )
        host = self.POSTGRES_HOST.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
        return {
            "type": "postgresql",
            "host": host,
            "port": self.POSTGRES_PORT,
            "database": self.POSTGRES_DB,
            "login": self.POSTGRES_USER,
            "password": self.POSTGRES_PASSWORD,
        }

    @property
    def postgres_enabled(self) -> bool:
        """
        Purpose:
            Determines whether PostgreSQL is fully configured.

        Returns:
            bool: True when host, user, and password are set.
        """
        return bool(self.POSTGRES_HOST and self.POSTGRES_USER and self.POSTGRES_PASSWORD)

    def get_fhir_staging_config(self) -> dict:
        """
        Purpose:
            Packages fhir-staging service connection settings into a config dict.

        Returns:
            dict: base_url, timeout — ready for FhirStagingClient.
        """
        return {
            "base_url": self.FHIR_STAGING_BASE_URL,
            "timeout": 30.0,
        }

    def get_embedding_config(self) -> dict:
        """
        Purpose:
            Packages embedding provider settings into a config dict.

        Returns:
            dict: provider, model, dimensions, tasks, batch_size,
                  max_retries, base_backoff — ready for the embedding provider.
        """
        return {
            "provider": self.EMBEDDING_PROVIDER,
            "model": self.JINA_MODEL,
            "dimensions": self.JINA_DIMENSIONS,
            "tasks": {
                "passage": self.JINA_TASK_PASSAGE,
                "query": self.JINA_TASK_QUERY,
            },
            "batch_size": self.JINA_BATCH_SIZE,
            "max_retries": self.JINA_MAX_RETRIES,
            "base_backoff": self.JINA_BASE_BACKOFF,
        }

    def get_jina_config(self) -> dict:
        """
        Purpose:
            Packages Jina API connection settings into a config dict.

        Returns:
            dict: base_url, api_key, timeout — ready for JinaConnector.
        """
        return {
            "base_url": self.JINA_BASE_URL,
            "api_key": self.JINA_API_KEY,
            "timeout": self.JINA_TIMEOUT,
        }

    def get_opensearch_config(self) -> dict:
        """
        Purpose:
            Packages OpenSearch connection settings into a config dict.

        Returns:
            dict: schema, host, port, login, password, verify_certs,
                  ca_certs, index_name — ready for OpensearchConnector.
        """
        return {
            "schema": self.OPENSEARCH_SCHEMA,
            "host": self.OPENSEARCH_HOST,
            "port": self.OPENSEARCH_PORT,
            "login": self.OPENSEARCH_LOGIN,
            "password": self.OPENSEARCH_PASSWORD,
            "verify_certs": self.OPENSEARCH_VERIFY_CERTS,
            "ca_certs": self.OPENSEARCH_CA_CERTS,
            "index_name": self.OPENSEARCH_INDEX_NAME,
        }

    def get_chunking_config(self) -> dict:
        """
        Purpose:
            Packages chunker settings into a config dict.

        Returns:
            dict: max_chars, overlap_chars — ready for ClinicalDocumentChunker.
        """
        return {
            "max_chars": self.CHUNK_MAX_CHARS,
            "overlap_chars": self.CHUNK_OVERLAP_CHARS,
        }

    @property
    def indexing_enabled(self) -> bool:
        """
        Purpose:
            Determines whether the document-chat indexing layer is configured.

        Returns:
            bool: True when Jina and OpenSearch are both fully configured.
        """
        return bool(
            self.JINA_API_KEY
            and self.OPENSEARCH_HOST
            and self.OPENSEARCH_LOGIN
            and self.OPENSEARCH_PASSWORD
        )

