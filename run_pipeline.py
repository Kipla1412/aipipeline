"""
End-to-end Medical Pipeline:
  NAS PDFs → Extract → Classify → Transform → MedicalDocument
                                                ├─► Wiki Generator
                                                ├─► Metadata Repository
                                                └─► Graph Builder

Usage:
  python run_pipeline.py

Drop medical PDFs into storage/pdf/ and run.
"""

import hashlib
import sys
import asyncio
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.components.utils.config import PipelineConfig
from src.components.connectors.nas import NASConnector
from src.components.extractors.pymu_extractor import PyMuPdfExtractor
from src.components.extractors.image_analyzer import ImageAnalyzer
from src.components.transformers.medical_transformer import MedicalTransformer
from src.components.transformers.medical_classifier import MedicalClassifier
from src.components.generators.wiki_generator_wrapper import WikiGenerator
from src.components.graphbuilder.graphify_builder import GraphifyyBuilder
from src.components.metadata.json_repository import JsonMetadataRepository
from src.components.metadata.generator import MetadataGenerator

settings = PipelineConfig()
settings.initialize_system_directories()


def _get_processed_files() -> set[str]:
    log = settings.WIKI_OUTPUT_DIR / "log.md"
    if not log.exists():
        return set()
    text = log.read_text(encoding="utf-8")
    return set(re.findall(r"\*\*Source File:\*\*\s*\n\s*\n\s+(.+\.pdf)", text))


def _make_document_id(filepath: Path) -> str:
    h = hashlib.sha256(filepath.name.encode()).hexdigest()[:12]
    return f"{filepath.stem}:{h}"


async def main():
    connector = NASConnector(settings.get_connector_config())
    session = await connector.connect()
    all_files = session.get_new_files()
    processed = _get_processed_files()

    new_files = [f for f in all_files if f.name not in processed]
    skipped = len(all_files) - len(new_files)

    print(f"Found {len(all_files)} file(s) in {settings.RAW_PDF_DIR}")
    if skipped:
        print(f"Skipping {skipped} already-processed file(s)")
    if new_files:
        print(f"Processing {len(new_files)} new file(s)\n")
    else:
        print("No new files to process.")
        await connector.close()
        return

    extractor = PyMuPdfExtractor(settings.get_extractor_config())
    transformer = MedicalTransformer(settings.get_transformer_config())
    image_analyzer = ImageAnalyzer({"api_key": settings.OPENAI_API_KEY})
    classifier = MedicalClassifier({"api_key": settings.OPENAI_API_KEY, "model": "gpt-4o-mini"})
    wiki = WikiGenerator(settings.get_wiki_generator_config())
    metadata_gen = MetadataGenerator()
    repo = JsonMetadataRepository(settings.METADATA_INDEX_PATH)
    graph = GraphifyyBuilder({"target_dir": str(settings.WIKI_OUTPUT_DIR)})

    all_documents: list[dict] = []

    for filepath in new_files:
        print(f"Processing: {filepath.name}")
        extracted = extractor.extract(str(filepath))
        print(f"  Extracted: {len(extracted.markdown)} chars, {len(extracted.images)} images")

        if extracted.images:
            print(f"  Analyzing {len(extracted.images)} image(s)...")
            image_descriptions = await image_analyzer.extract(extracted.images)
            full_text = image_descriptions + "\n\n" + extracted.markdown
        else:
            full_text = extracted.markdown

        document = await transformer.transform(full_text)
        document["document_id"] = _make_document_id(filepath)
        document["report_type"] = await classifier.classify(extracted.markdown)
        document["images"] = extracted.images

        print(f"  Transformed: type={document['report_type']}")

        paths = wiki.generate(document, filepath.name)
        print(f"  Wiki pages: {len(paths)}")

        for entry in metadata_gen.generate(document):
            await repo.upsert(entry)
        print(f"  Metadata entries: {len(metadata_gen._entries)}")

        all_documents.append(document)

    await repo._flush()
    await connector.close()

    print("\nBuilding knowledge graph...")
    graph.build_from_documents(all_documents)
    print("Done.\n")


if __name__ == "__main__":
    asyncio.run(main())
