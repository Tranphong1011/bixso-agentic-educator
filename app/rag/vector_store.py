from dataclasses import dataclass
from uuid import uuid5
from uuid import NAMESPACE_URL

from qdrant_client import QdrantClient
from qdrant_client.models import Distance
from qdrant_client.models import FieldCondition
from qdrant_client.models import Filter
from qdrant_client.models import MatchValue
from qdrant_client.models import PointStruct
from qdrant_client.models import VectorParams

from app.core.config import settings


@dataclass(frozen=True)
class IndexedChunk:
    chunk_id: str
    content: str
    vector: list[float]
    payload: dict


def build_qdrant_client() -> QdrantClient:
    if not settings.QDRANT_URL:
        raise ValueError("QDRANT_URL is required for Qdrant connection.")
    return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)


def ensure_collection(vector_size: int) -> None:
    client = build_qdrant_client()
    collection_name = settings.QDRANT_COLLECTION
    exists = client.collection_exists(collection_name=collection_name)
    if exists:
        return

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def build_point_id(document_id: str, chunk_index: int) -> str:
    # Deterministic UUID so re-indexing the same chunk replaces old vectors.
    return str(uuid5(NAMESPACE_URL, f"{document_id}:{chunk_index}"))


def upsert_document_chunks(chunks: list[IndexedChunk]) -> None:
    if not chunks:
        return

    points = [
        PointStruct(id=chunk.chunk_id, vector=chunk.vector, payload=chunk.payload)
        for chunk in chunks
    ]
    client = build_qdrant_client()
    client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)


def search_user_chunks(
    query_vector: list[float],
    user_id: str,
    top_k: int = 5,
    file_name: str | None = None,
) -> list[dict]:
    conditions = [FieldCondition(key="user_id", match=MatchValue(value=user_id))]
    if file_name:
        conditions.append(FieldCondition(key="file_name", match=MatchValue(value=file_name)))

    client = build_qdrant_client()
    if hasattr(client, "search"):
        results = client.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=query_vector,
            query_filter=Filter(must=conditions),
            limit=top_k,
            with_payload=True,
        )
    else:
        # Compatibility path for newer qdrant-client APIs.
        response = client.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=query_vector,
            query_filter=Filter(must=conditions),
            limit=top_k,
            with_payload=True,
        )
        results = response.points
    return [
        {
            "score": item.score,
            "payload": item.payload,
        }
        for item in results
    ]
