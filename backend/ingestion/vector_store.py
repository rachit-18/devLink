from __future__ import annotations

import os
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models

from backend.ingestion.embeddings import embedding_dimension

DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "devlink_code_chunks")


class QdrantStore:
    def __init__(self) -> None:
        self.client = QdrantClient(
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            api_key=os.getenv("QDRANT_API_KEY"),
        )
        self.collection_name = DEFAULT_COLLECTION

    def ensure_collection(self) -> None:
        collections = self.client.get_collections().collections
        if any(collection.name == self.collection_name for collection in collections):
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=embedding_dimension(),
                distance=models.Distance.COSINE,
            ),
        )

    def upsert_chunks(self, chunks: list[dict[str, Any]], vectors: list[list[float]]) -> int:
        self.ensure_collection()
        points = []
        for chunk, vector in zip(chunks, vectors, strict=False):
            points.append(
                models.PointStruct(
                    id=chunk["chunk_id"],
                    vector=vector,
                    payload=chunk,
                )
            )
        if points:
            self.client.upsert(collection_name=self.collection_name, points=points)
        return len(points)

    def search(self, vector: list[float], limit: int = 5) -> list[dict[str, Any]]:
        self.ensure_collection()
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )
        matches: list[dict[str, Any]] = []
        for result in results:
            payload = result.payload or {}
            payload["score"] = result.score
            matches.append(payload)
        return matches

    def list_files(self) -> list[dict[str, Any]]:
        self.ensure_collection()
        seen: dict[str, dict[str, Any]] = {}
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=None,
                limit=100,
                with_payload=True,
                offset=offset,
            )
            for point in points:
                payload = point.payload or {}
                file_path = payload.get("file_path")
                if not file_path:
                    continue
                seen.setdefault(
                    file_path,
                    {
                        "file_path": file_path,
                        "language": payload.get("language", "text"),
                    },
                )
            if offset is None:
                break
        return sorted(seen.values(), key=lambda item: item["file_path"])

    def get_file_payload(self, file_path: str) -> dict[str, Any] | None:
        self.ensure_collection()
        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="file_path", match=models.MatchValue(value=file_path))]
            ),
            limit=100,
            with_payload=True,
        )

        if not points:
            return None

        chunks = [point.payload for point in points if point.payload]
        chunks = sorted(chunks, key=lambda item: (item.get("start_line", 0), item.get("end_line", 0)))
        full_content = "\n\n".join(chunk.get("content", "") for chunk in chunks)
        first = chunks[0]
        return {
            "file_path": file_path,
            "language": first.get("language", "text"),
            "chunks": chunks,
            "content": full_content,
        }
