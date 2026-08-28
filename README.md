# AI Platform

This project is a data platform designed to extract, transform, and load data from various sources into a centralized system, primarily Elasticsearch. It uses Apache Airflow to orchestrate these data pipelines and includes a custom-built framework for handling different data operations. The platform is designed to process both structured and unstructured data, with capabilities for generating semantic embeddings for advanced search and analysis.

Project Structure
~~~~~~~~~~~~~~~~~

The project is organized into several key directories:

- src/: Contains the core source code for the platform.
- dags/: Holds the Apache Airflow DAGs that define and orchestrate the data pipelines.
- tests/: Includes unit tests for the custom modules.

src/custom
~~~~~~~~~~

This directory contains a modular and extensible framework for building ETL pipelines. It is organized by functionality:

- connectors/: Manages connections to various data sources. It includes a ConnectorFactory to instantiate connectors for different services like Arxiv, Elasticsearch, Gmail, Opensearch, and RDBMS.

- credentials/: Handles credential management. It provides a CredentialFactory to retrieve credentials from different providers, with a primary implementation for AirflowCredentials which fetches credentials from Airflow's connection manager.

- extractors/: Contains the logic for extracting data from the sources defined in the connectors directory. It includes extractors for Gmail, RDBMS, and Arxiv, with a factory for easy instantiation.

- loaders/: Responsible for loading data into the target systems. It includes SingleIngestor and BulkIngestor for Elasticsearch, and integrates with txtai for generating embeddings.

- transformers/: Handles data transformation. It includes a DocumentTransformer for unstructured text and a JsonTransformer for structured data, preparing the data for loading.

- utils/: Provides utility functions for file reading (reader.py) and resilience patterns like rate limiting and retries (resilience.py).

src/txtai
~~~~~~~~

This directory contains a git submodule for txtai, an all-in-one AI framework for semantic search, LLM orchestration, and language model workflows. It is used in this project primarily for its embedding generation capabilities. For more details, refer to the README.md within that directory.

dags
~~~~

This directory contains the Airflow DAGs that orchestrate the data pipelines.

- structure/health/: A pipeline that extracts data from a PostgreSQL database, transforms it, and loads it into Elasticsearch. The pipeline is configured via YAML files in its config directory.

- unstructure/gmail/: A pipeline that extracts data from Gmail, processes the text and attachments, generates embeddings, and loads the results into Elasticsearch.

- unstructure/arxiv/: A pipeline that connects to the Arxiv API to fetch research paper metadata and PDFs.

tests
~~~~~

This directory contains unit tests for the custom framework components, ensuring the reliability of the connectors, credentials, loaders, transformers, and utils.

Key Features
~~~~~~~~~~~~

- Modular ETL Framework: The custom framework in `src/custom` is designed to be modular and easily extensible.
- Factory Patterns: The use of factory patterns allows for easy addition of new connectors, extractors, and loaders.
- Support for Structured and Unstructured Data: The platform can handle both tabular data from databases and unstructured text from sources like emails and academic papers.
- Semantic Search: Integration with `txtai` enables the generation of vector embeddings for powerful semantic search capabilities.
- Airflow Orchestration: Data pipelines are defined and managed as Airflow DAGs, providing scheduling, monitoring, and logging.
- Configuration-Driven Pipelines: The pipelines are configured using YAML files, making them easy to manage and modify without changing the core code.

source:     arxiv
            url - pdf url - parse content (arxiv id, text, meta data) - **Embedding** (jina) (arxiv id, text, meta data, vector) - elastic search

            gmail
            attachments - parse content (email id, text, meta data) - **Embedding** (txtai) (email id, text, meta data, vector) - elasticsearch

            rdbms
            postgresql - extract data - transformer - **Embeddings** - elasticsearch

search:     user query - **Embedding** (jina) - llm - agents - hybrid search - retrieve - hello + vector - elasticsearch - Ans:-

---

# Current Usage (Medical Platform Additions)

The platform has grown beyond ETL into an AI-native medical document processing pipeline: ingesting **PDFs, DICOMs, and cloud-hosted files**, extracting structured clinical information with **LLMs**, and building multiple knowledge representations — a patient-centric **Wiki**, a **knowledge graph** (JSON / ArangoDB / Neo4j), a searchable **metadata index**, and an **EMR clinical pipeline** producing **HL7 FHIR R4** resources after human review.

```
Medical Documents (PDF / DICOM / FileNest)
        │
        ▼
Extractors (PyMuPDF, DICOM)
        │
        ▼
Medical Classifier (14 report types)
        │
        ▼
Medical Transformer (LLM + structured output)
        │
        ├───────────────┬──────────────────────┐
        ▼               ▼                      ▼
  Wiki Generator   Metadata Index        EMR Clinical Pipeline
  (markdown KB)    (index.json)          (staging → review → FHIR)
        │               │                      │
        ▼               ▼                      ▼
  Graph Builder    Graph-RAG Query      FHIR R4 Bundle
  (JSON/ArangoDB/   (query.py)          (storage/emr/fhir)
   Neo4j)
```

## Key Features (Medical)

- **LLM-powered clinical extraction** — OpenAI structured outputs produce a typed Clinical Domain Model (Patient, Diagnosis, Medication, Procedure, Observation, ImagingStudy)
- **Unified Observation model** — every measurable value (labs, vitals, ECG, imaging) becomes a structured Observation with numeric values, units, reference ranges, and interpretation
- **Multiple graph backends** — the same in-memory Graph object persists to JSON, ArangoDB (cloud), or Neo4j (local/cloud) via interchangeable repositories
- **Patient-centric Wiki** — Obsidian-style markdown knowledge base with `[[wikilinks]]`, patient timelines, and 14 report-type plugins
- **Human-in-the-Loop EMR pipeline** — AI output is a *draft*; clinical review (edit/approve/reject) with full audit trail; only **approved** records become FHIR
- **Typed FHIR R4** — `fhir.resources` mappers produce validated Patient, Observation (with LOINC codes), Condition, MedicationRequest, Procedure, DiagnosticReport, ImagingStudy, assembled into a Bundle
- **FileNest read/download** — connect to cloud file storage, list files, generate signed URLs, download into a temp staging folder
- **Clean architecture** — factories, ABC interfaces, dependency injection, SOLID, DDD-style domain models, YAML/`.env` configuration

## Component Layers (`src/components/`)

| Layer | Responsibility | Key files |
|-------|---------------|-----------|
| **connectors/** | Infrastructure: validate config, create client, health check, lifecycle. No business logic. | `base.py`, `factory.py`, `nas.py`, `s3.py`, `arango.py`, `neo4j.py`, `filenest.py`, ... |
| **extractors/** | Pull data from sources: PDF → markdown+images, DICOM → metadata, FileNest → download | `pymu_extractor.py`, `dicom.py`, `image_analyzer.py`, `filenest.py` |
| **transformers/** | LLM extraction → Clinical Domain Model. Builder → Normalizer → Validator pipeline | `medical_transformer.py`, `medical_classifier.py`, `builders/`, `normalizers/`, `validators/`, `models/` |
| **generators/** | Patient-centric wiki generation, 14 report-type plugins | `wiki_generator.py`, `plugin_base.py`, `composer.py`, `plugins/` |
| **graphbuilder/** | Pure graph construction (MedicalDocument → Graph) + pluggable persistence | `medical_graph_builder.py`, `models.py`, `repository/{json,arango,neo4j}_repository.py` |
| **metadata/** | Searchable entity index (JSON with atomic writes) | `models.py`, `json_repository.py`, `generator.py` |
| **emr/** | Clinical staging, human review, audit trail, FHIR mapping | `staging/`, `review/`, `fhir/` (mappers + bundle), `repository/` |
| **indexing/** | Document-chat indexing: Clinical JSON → semantic chunks → Jina embeddings → OpenSearch | `chunker.py`, `indexer.py`, `factory.py`, `embeddings/jina.py`, `repository/opensearch.py` |
| **utils/** | LLM client, Pydantic config, resilience | `llm.py`, `config.py`, `resilience.py` |

## Installation

**Option A — uv (recommended)** — uv manages everything from `pyproject.toml` + `uv.lock`:

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
#    or: pip install uv

# 2. Clone & sync dependencies (creates .venv, installs FileNest SDK from local path)
git clone <repo-url>
cd aiplatform
uv sync

# 3. Activate the venv
source .venv/bin/activate

# 4. Environment — copy the template and fill in real values
cp .env.example .env
```

**Option B — pip / venv (classic)**

```bash
git clone <repo-url>
cd aiplatform
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Internal SDK (FileNest)** — not on PyPI, install from local checkout:

```bash
pip install -e /home/kipla/filenest-python-sdk
```

**Environment** — copy `.env.example` into `.env` at the project root:

```bash
cp .env.example .env
```

`.env.example` contains all required keys (OpenAI, FileNest, Postgres, ArangoDB, Neo4j) with placeholder values:

```bash
# LLM
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1

# ArangoDB (cloud or local)
ARANGO_HOST=your-cluster.arangodb.cloud
ARANGO_PORT=8529
ARANGO_USERNAME=root
ARANGO_PASSWORD=...
ARANGO_DATABASE=medical_graph

# Neo4j (local Docker or cloud)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...
NEO4J_DATABASE=neo4j

# FileNest (cloud file storage)
FILENEST_API_KEY=...
FILENEST_PROJECT_ID=...
FILENEST_API_URL=...
```

## Usage

### Full wiki + graph pipeline

```bash
# Put PDFs/DICOMs in storage/raw/, then:
python3 run_pipeline.py
```

Output: `storage/wiki/` (markdown), `storage/wiki/graph.json`, `storage/metadata/index.json`, ArangoDB + Neo4j populated (if configured).

### EMR clinical pipeline (no wiki, no graph)

```bash
python3 run_emr.py "Blood Report - Thomas Reynolds.pdf"           # extract → transform → stage
python3 run_emr.py "Blood Report - Thomas Reynolds.pdf" --approve  # + approve + FHIR
```

Output: `storage/emr/staging/{id}.json`, `storage/emr/fhir/{id}.json`.

### Review staged records interactively

```bash
python3 review_emr.py              # list staged records
python3 review_emr.py <record_id>  # review, edit, approve/reject
```

### FileNest — list & download cloud files

```bash
python3 tests/manual/test_filenest_download.py
python3 tests/manual/test_filenest_download.py <file_id>
```

Downloads land in `storage/temp/`.

### FileNest — full flow (connector → URL → download → Postgres)

```bash
# Single file (first in list, or pass a file id)
python3 tests/manual/test_filenest_full_flow.py
python3 tests/manual/test_filenest_full_flow.py <file_id>

# All files, one by one, in a single run
python3 tests/manual/test_filenest_full_flow.py --all
```

Each file: signed URL → download to `storage/temp/` → save metadata to PostgreSQL → mark `downloaded`.

### Graph-RAG query

```bash
export OPENAI_API_KEY=sk-...
python3 query.py "what medications does Robert Chen take?"
```

### Graph backend connectivity checks

```bash
python3 check_arango.py
python3 check_neo4j.py
```

### Document chat indexing (Clinical JSON → chunks → embeddings → OpenSearch)

The indexing layer is separate from FHIR persistence. It converts Clinical Domain Model JSON into semantic, structure-aware chunks (one per summary/diagnosis/observation/medication/procedure/imaging/section), embeds them via the existing Jina provider, and upserts them into OpenSearch with deterministic chunk IDs (idempotent — re-indexing never duplicates).

```bash
# Unit tests (mock-based, no credentials)
python3 -m pytest tests/test_custom/test_indexing/ -q

# Build an indexer from config (.env): chunker + Jina + OpenSearch
python3 -c "
from src.components.indexing import IndexingFactory
indexer = IndexingFactory.create_indexer()
print(indexer.index(CLINICAL_JSON, {'patient_id': '10001', 'file_id': 'ABC123', 'source_file': 'r.pdf'}))
"
```

Retrieval filters by `patient_id` AND `file_id` (stored as structured OpenSearch keyword fields) before kNN vector search, so document chat answers are grounded to a specific patient + document.

Two Airflow DAGs drive this:
- `clinical_document_indexer` — indexes already-transformed Clinical JSON (`storage/emr/transformed/*.json`)
- `direct_document_indexer` — downloads a FileNest file directly, extracts (PDF/image/DICOM), and indexes the extracted text (no classification, no Clinical Domain transformation, no FHIR)

Embedding/OpenSearch/chunking settings live in `.env` (`JINA_*`, `OPENSEARCH_*`, `CHUNK_*`); in Airflow, Jina/OpenSearch/FileNest/OpenAI credentials come from Airflow Connections (`jina_api`, `opensearch_api`, `filenest_conn_id`, `openai`).

## Airflow DAGs (`dags/`)

| DAG | Path | Flow |
|-----|------|------|
| `medical_pipeline` | `unstructure/medical/medical.py` | NAS → extract → classify → transform → wiki → graph (+Neo4j) |
| `emr_transformer_pipeline` | `unstructure/emr/emr.py` | NAS → extract → classify → transform → Clinical Domain Model JSON |
| `arxiv_full_pipeline` | `unstructure/arxiv/arxiv.py` | Arxiv → PDF → Docling → chunk → embed → ES |
| `gmail_data_pipeline` | `unstructure/gmail/gmail.py` | Gmail → chunk → embed → ES |
| `health_data_pipeline` | `structure/health/health.py` | PostgreSQL → JSON → ES |
| `spark_*` | `spark/`, `structure/aws/` | Spark ETL → ES |
| `filenest_ingest` | `unstructure/filenest/asset_producer.py` | FileNest → list → download → Postgres → emit Asset |
| `filenest_process` | `unstructure/filenest/asset_consumer.py` | Asset-triggered → extract → classify → transform |
| `clinical_document_indexer` | `unstructure/indexing/asset_indexer.py` | Clinical JSON → chunk → Jina embed → OpenSearch |
| `direct_document_indexer` | `unstructure/indexing/direct_document_indexer.py` | FileNest download → extract → chunk → Jina embed → OpenSearch (no classification/transform) |

### Airflow setup

Airflow runs from its **own venv** — separate from the project's uv venv:

```bash
# 1. Install Airflow 3 + providers into the Airflow venv
/home/kipla/airflow/venv/bin/pip install apache-airflow==3.1.5
/home/kipla/airflow/venv/bin/pip install "apache-airflow-providers-standard"
/home/kipla/airflow/venv/bin/pip install "apache-airflow-providers-postgres"
/home/kipla/airflow/venv/bin/pip install -e /home/kipla/filenest-python-sdk
/home/kipla/airflow/venv/bin/pip install psycopg2-binary sqlalchemy pydantic python-dotenv

# 2. Point Airflow at this repo's dags/ folder
export AIRFLOW_HOME=/home/kipla/airflow
#    dags_folder = /home/kipla/aipipeline/aiplatform/dags  (in airflow.cfg)

# 3. The DAGs read credentials from this project's .env automatically.
#    No Airflow Connections required for FileNest/Postgres.
```

The DAGs use **Airflow 3 Assets** (`from airflow.sdk import Asset`):
- `filenest_ingest` (producer) emits an Asset when downloaded files exist in PostgreSQL
- `filenest_process` (consumer) triggers on that Asset → processes the files

## Testing

```bash
# Unit tests
python3 -m pytest tests/test_custom/ -v
python3 -m pytest tests/test_emr/ -v
python3 -m pytest tests/test_filenest/ -v

# Real end-to-end tests (live LLM calls, real PDFs/DICOMs)
python3 test_transformer.py "Blood Report - Thomas Reynolds.pdf"
python3 test_pdf_json.py "Chest X-Ray - Robert Chen.pdf"
python3 test_emr_flow.py "Blood Report - Thomas Reynolds.pdf"   # stops before staging
python3 test_emr_flow.py "CT_small.dcm"                         # DICOM
```

## Verification

Run these to confirm the pipeline is working end-to-end:

### 1. Unit tests (mock-based, no credentials)

```bash
uv run --group dev python -m pytest tests/ -q
```

Targeted suites:

```bash
uv run --group dev python -m pytest tests/test_fhir_staging/ -q      # staging bridge (mapper/client/push)
uv run --group dev python -m pytest tests/test_filenest/ -q          # FileNest connector/downloader
uv run --group dev python -m pytest tests/test_filenest_repository/ -q  # PostgreSQL persistence
```

### 2. fhir-staging bridge check (requires the service running on :8002)

```bash
python3 tests/manual/check_staging.py
```

Checks: config reads `FHIR_STAGING_BASE_URL` → service health → client+mapper construct → create+PATCH a test record → list completed records. Prints `✓ fhir-staging bridge is WORKING` when green.

### 3. Airflow DAG import check (requires Airflow venv)

```bash
/home/kipla/airflow/venv/bin/python -m py_compile dags/unstructure/filenest/asset_producer.py
/home/kipla/airflow/venv/bin/python -m py_compile dags/unstructure/filenest/asset_consumer.py
```

### 4. View staged records

```bash
curl -s "http://localhost:8002/api/v1/staging-records/?status=completed"
```

Clean human-readable view (values + reference ranges):

```bash
curl -s "http://localhost:8002/api/v1/staging-records/10011" | python3 -c "
import sys, json
r = json.load(sys.stdin)
print(f'Record {r[\"id\"]} — {r.get(\"attachment_title\")} [{r.get(\"status\")}]')
for o in r.get('observations', []):
    print(f'  {o.get(\"code_display\")}: {o.get(\"value_quantity_value\")} {o.get(\"value_quantity_unit\")}')
"
```

Interactive API docs: `http://localhost:8002/docs`

### Dependencies via uv

```bash
uv sync --group dev            # install everything (incl. dev: pytest)
uv run python -c "import sys; print(sys.version)"   # sanity check
```

The internal `filenest-python-sdk` is pinned to a local path in `pyproject.toml` (`[tool.uv.sources]`) — `uv sync` installs it from there automatically.

## Storage Layout

```
storage/
├── raw/          # Source documents (PDF/DICOM) — ingest queue
├── images/       # Extracted images for LLM vision analysis
├── temp/         # FileNest download staging
├── wiki/         # Generated patient wiki (markdown)
│   ├── Patients/{slug}/{patient,index,timeline,Reports,Images}.md
│   ├── Doctors/ Diseases/ Medications/ Procedures/ Hospitals/
│   └── graph.json
├── metadata/     # index.json — entity search index
└── emr/
    ├── staging/      # Draft clinical records (workflow states)
    ├── transformed/  # Clinical Domain Model JSON
    └── fhir/         # FHIR R4 Bundles (approved records only)
```

## Human-in-the-Loop (EMR)

```
LLM output (AI draft)
    │
    ▼
Staging: draft → pending_review → in_review → needs_correction
    │
    ├── approve → Approved Clinical Record (immutable snapshot)
    │         │
    │         ▼
    │    FHIR Mapping Layer → FHIR R4 Bundle
    │         │
    │         ▼
    │    FHIR Repository (local JSON / HAPI later)
    │
    └── reject → Rejected
```

Every edit records an audit entry: reviewer, timestamp, field, old→new value, reason. Only **Approved** records ever reach FHIR generation.
