"""Graph-RAG query over the medical knowledge base.

Pure aiplatform — zero aipipeline dependency.

Usage:
  export OPENAI_API_KEY=sk-...
  python query.py                           # interactive chat
  python query.py "what meds for Alice?"    # single question

Storage defaults: aiplatform/storage/wiki, aiplatform/storage/metadata/index.json
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.components.utils.llm import LLMClient
from src.components.metadata.json_repository import JsonMetadataRepository
from src.components.metadata.models import SearchQuery, EntityType, MetadataEntry
from src.components.graphbuilder.graphify_builder import GraphifyyBuilder

WIKI_DIR = Path(os.getenv("WIKI_DIR", str(Path(__file__).resolve().parent / "storage" / "wiki")))
META_PATH = Path(os.getenv("METADATA_PATH", str(Path(__file__).resolve().parent / "storage" / "metadata" / "index.json")))
GRAPH_PATH = WIKI_DIR / "graph.json"


async def _load_wiki_page(slug: str) -> str:
    """Load a wiki markdown page by slug (fuzzy match on filename)."""
    for md in WIKI_DIR.rglob("*.md"):
        if slug.lower() in md.stem.lower():
            return md.read_text(encoding="utf-8")[:3000]
    return ""


async def _graph_neighbors(entity: str, graph_builder: GraphifyyBuilder, depth: int = 1) -> str:
    """Query graphify for neighbors of an entity."""
    try:
        result = graph_builder.query(f"neighbors of {entity}", budget=1000)
        return result[:2000]
    except Exception:
        return ""


async def retrieve(question: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    model = os.getenv("LLM_MODEL_NAME", "gpt-4o-mini")
    llm = LLMClient(api_key=api_key, model=model)
    repo = JsonMetadataRepository(META_PATH)
    graph = GraphifyyBuilder({"target_dir": str(WIKI_DIR)})

    repo._ensure_loaded()

    # 1. Find matching entities by scanning every word against every label
    entities: List[MetadataEntry] = []
    seen_ids: set = set()
    words = [w.rstrip("?!.,;:-\"'") for w in question.lower().split() if len(w.rstrip("?!.,;:-\"'")) >= 3]

    for label, ids in repo._by_label.items():
        for word in words:
            if word in label:
                for eid in ids:
                    if eid not in seen_ids and eid in repo._entries:
                        seen_ids.add(eid)
                        entities.append(repo._entries[eid])

    # 2. Load wiki context for matched entities
    wiki_blocks: List[str] = []
    seen = set()
    for e in entities[:6]:
        if e.label in seen:
            continue
        seen.add(e.label)
        page = await _load_wiki_page(e.slug or e.label)
        if page:
            wiki_blocks.append(f"--- {e.label} ({e.entity_type.value}) ---\n{page}")

    # 3. Graph context for top entities
    graph_context = ""
    for e in entities[:3]:
        gc = await _graph_neighbors(e.label, graph)
        if gc:
            graph_context += f"\nGraph neighbors of {e.label}:\n{gc}\n"

    # 4. LLM answer
    context = "\n\n".join(wiki_blocks) + graph_context
    if not context.strip():
        context = "No matching entities found in the knowledge base."

    llm_context = context[:12000] if len(context) > 12000 else context

    prompt = f"""You are a medical knowledge assistant. Answer questions using ONLY the context below.
If the context doesn't contain the answer, say so clearly.

=== KNOWLEDGE BASE CONTEXT ===
{context[:8000]}

=== QUESTION ===
{question}

=== ANSWER ==="""

    response = await llm.generate(
        f"""You are a medical knowledge assistant. Answer questions using ONLY the context below.

=== KNOWLEDGE BASE CONTEXT ===
{llm_context}""",
        question,
    )
    await llm.close()

    sources = [f"{e.label} ({e.entity_type.value})" for e in entities[:5]]
    return {"answer": response, "sources": sources, "entity_count": len(entities)}


async def interactive():
    print("═" * 50)
    print("  Medical Graph-RAG — aiplatform")
    print(f"  Wiki: {WIKI_DIR}")
    print(f"  Index: {META_PATH}")
    print("  Type 'exit' to stop")
    print("═" * 50)

    while True:
        try:
            q = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if not q:
            continue
        if q.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        print("▸ Searching...")
        result = await retrieve(q)
        print(f"\n{result['answer']}")
        if result["sources"]:
            print(f"\n  Sources: {', '.join(result['sources'])}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        result = asyncio.run(retrieve(question))
        print(f"\n{result['answer']}")
        if result["sources"]:
            print(f"\nSources: {', '.join(result['sources'])}")
    else:
        asyncio.run(interactive())
