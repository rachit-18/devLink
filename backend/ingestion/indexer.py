from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.ingestion.chunker import chunk_repository
from backend.ingestion.embeddings import embed_texts
from backend.ingestion.vector_store import QdrantStore


class CodeIndexer:
    def __init__(self) -> None:
        self.store = QdrantStore()

    def index_path(self, root_path: Path) -> dict[str, Any]:
        chunks = chunk_repository(root_path)
        if not chunks:
            return {"indexed_files": 0, "indexed_chunks": 0}

        payloads = [chunk.to_payload() for chunk in chunks]
        vectors = embed_texts([chunk.content for chunk in chunks])
        stored = self.store.upsert_chunks(payloads, vectors)
        indexed_files = len({chunk.file_path for chunk in chunks})
        return {"indexed_files": indexed_files, "indexed_chunks": stored}

    def search(self, question: str, limit: int = 5) -> list[dict[str, Any]]:
        query_vector = embed_texts([question])[0]
        return self.store.search(query_vector, limit=limit)

    def list_files(self) -> list[dict[str, Any]]:
        return self.store.list_files()

    def get_file_payload(self, file_path: str) -> dict[str, Any] | None:
        return self.store.get_file_payload(file_path)
