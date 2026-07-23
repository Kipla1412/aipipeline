"""JSON-backed metadata repository with atomic writes and in-memory caching."""

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from .repository import AbstractMetadataRepository
from .models import MetadataEntry, EntityType, SearchResult, SearchQuery

logger = logging.getLogger(__name__)


class JsonMetadataRepository(AbstractMetadataRepository):
    def __init__(self, index_path: Path):
        self._path = Path(index_path)
        self._entries: dict[str, MetadataEntry] = {}
        self._by_type: dict[str, list[str]] = {}
        self._by_label: dict[str, list[str]] = {}
        self._loaded = False

    async def upsert(self, entry: MetadataEntry) -> None:
        self._ensure_loaded()
        self._entries[entry.id] = entry
        self._by_type.setdefault(entry.entity_type.value, [])
        if entry.id not in self._by_type[entry.entity_type.value]:
            self._by_type[entry.entity_type.value].append(entry.id)
        self._by_label.setdefault(entry.label.lower(), [])
        if entry.id not in self._by_label[entry.label.lower()]:
            self._by_label[entry.label.lower()].append(entry.id)

    async def get_by_id(self, entity_id: str) -> MetadataEntry | None:
        self._ensure_loaded()
        return self._entries.get(entity_id)

    async def get_by_label(self, label: str, entity_type: EntityType | None = None) -> MetadataEntry | None:
        self._ensure_loaded()
        ids = self._by_label.get(label.lower(), [])
        for eid in ids:
            entry = self._entries.get(eid)
            if entry is None:
                continue
            if entity_type and entry.entity_type != entity_type:
                continue
            return entry
        return None

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        self._ensure_loaded()
        q = query.query.lower()
        results: list[SearchResult] = []
        for entry in self._entries.values():
            if query.entity_type and entry.entity_type != query.entity_type:
                continue
            if q in entry.label.lower():
                score = len(q) / len(entry.label) if entry.label else 0.0
                results.append(SearchResult(entry=entry, score=score))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[: query.limit]

    async def list_by_type(self, entity_type: EntityType) -> list[MetadataEntry]:
        self._ensure_loaded()
        ids = self._by_type.get(entity_type.value, [])
        return [self._entries[eid] for eid in ids if eid in self._entries]

    async def get_references(self, entity_id: str) -> list[MetadataEntry]:
        self._ensure_loaded()
        entry = self._entries.get(entity_id)
        if entry is None:
            return []
        resolved: list[MetadataEntry] = []
        for ref_label in entry.references:
            ref_entry = await self.get_by_label(ref_label)
            if ref_entry:
                resolved.append(ref_entry)
        return resolved

    async def build_from_wiki(self, wiki_dir: Path) -> int:
        from .indexer import MetadataIndexer
        self._entries.clear()
        self._by_type.clear()
        self._by_label.clear()
        self._loaded = True
        count = await MetadataIndexer(self).build_from_wiki(wiki_dir)
        await self._flush()
        return count

    async def build_from_documents(self, documents: list[dict]) -> int:
        from .generator import MetadataGenerator
        self._entries.clear()
        self._by_type.clear()
        self._by_label.clear()
        self._loaded = True
        gen = MetadataGenerator()
        count = 0
        for doc in documents:
            for entry in gen.generate(doc):
                await self.upsert(entry)
                count += 1
        await self._flush()
        return count

    async def clear(self) -> None:
        self._entries.clear()
        self._by_type.clear()
        self._by_label.clear()
        self._loaded = True
        if self._path.exists():
            self._path.unlink()

    async def stats(self) -> dict[str, int]:
        self._ensure_loaded()
        counts = {et: len(ids) for et, ids in self._by_type.items()}
        counts["total"] = len(self._entries)
        return counts

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self._path.exists():
            self._load()
        else:
            self._loaded = True

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._entries = {eid: MetadataEntry(**raw) for eid, raw in data.get("entries", {}).items()}
            self._by_type = data.get("by_type", {})
            self._by_label = data.get("by_label", {})
            self._loaded = True
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(f"Corrupt metadata index: {exc}. Starting fresh.")
            self._entries = {}
            self._by_type = {}
            self._by_label = {}
            self._loaded = True

    async def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "1.0.0",
            "last_built": datetime.now(timezone.utc).isoformat(),
            "entries": {eid: entry.model_dump() for eid, entry in self._entries.items()},
            "by_type": self._by_type,
            "by_label": self._by_label,
        }
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self._path.parent, suffix=".tmp", delete=False) as tmp:
            json.dump(payload, tmp, indent=2, ensure_ascii=False)
            tmp_name = tmp.name
        Path(tmp_name).replace(self._path)
