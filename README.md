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
| **utils/** | LLM client, Pydantic config, resilience | `llm.py`, `config.py`, `resilience.py` |

## Installation

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

**Environment** — copy into `.env` at the project root:

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

## Airflow DAGs (`dags/`)

| DAG | Path | Flow |
|-----|------|------|
| `medical_pipeline` | `unstructure/medical/medical.py` | NAS → extract → classify → transform → wiki → graph (+Neo4j) |
| `emr_transformer_pipeline` | `unstructure/emr/emr.py` | NAS → extract → classify → transform → Clinical Domain Model JSON |
| `arxiv_full_pipeline` | `unstructure/arxiv/arxiv.py` | Arxiv → PDF → Docling → chunk → embed → ES |
| `gmail_data_pipeline` | `unstructure/gmail/gmail.py` | Gmail → chunk → embed → ES |
| `health_data_pipeline` | `structure/health/health.py` | PostgreSQL → JSON → ES |
| `spark_*` | `spark/`, `structure/aws/` | Spark ETL → ES |

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
