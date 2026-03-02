from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import User
from app.db.models import UserDocument
from app.rag.chunking import chunk_text
from app.rag.document_loader import load_document_text
from app.rag.embeddings import embed_query
from app.rag.embeddings import embed_texts
from app.rag.vector_store import IndexedChunk
from app.rag.vector_store import build_point_id
from app.rag.vector_store import ensure_collection
from app.rag.vector_store import search_user_chunks
from app.rag.vector_store import upsert_document_chunks


@dataclass(frozen=True)
class RAGIngestionResult:
    document_id: str
    file_name: str
    total_chunks: int
    collection_name: str


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email))


def get_user_by_id(session: Session, user_id: str) -> User | None:
    return session.scalar(select(User).where(User.id == UUID(user_id)))


def _upsert_user_document_metadata(
    session: Session,
    user_id: UUID,
    file_name: str,
    storage_path: str,
    mime_type: str,
    file_size_bytes: int,
) -> UserDocument:
    existing = session.scalar(
        select(UserDocument).where(
            UserDocument.user_id == user_id,
            UserDocument.file_name == file_name,
        )
    )
    if existing:
        existing.storage_path = storage_path
        existing.mime_type = mime_type
        existing.file_size_bytes = file_size_bytes
        existing.qdrant_collection = settings.QDRANT_COLLECTION
        session.flush()
        return existing

    user_document = UserDocument(
        user_id=user_id,
        file_name=file_name,
        storage_path=storage_path,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        qdrant_collection=settings.QDRANT_COLLECTION,
    )
    session.add(user_document)
    session.flush()
    return user_document


def ingest_user_document(session: Session, user_id: str, file_path: str) -> RAGIngestionResult:
    if not settings.QDRANT_COLLECTION:
        raise ValueError("QDRANT_COLLECTION is required.")

    content, mime_type = load_document_text(file_path)
    chunks = chunk_text(
        content=content,
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )
    if not chunks:
        raise ValueError("No readable content found in document.")

    vectors = embed_texts(chunks)
    ensure_collection(vector_size=len(vectors[0]))

    file_name = Path(file_path).name
    path = Path(file_path)
    document = _upsert_user_document_metadata(
        session=session,
        user_id=UUID(user_id),
        file_name=file_name,
        storage_path=str(path.resolve()),
        mime_type=mime_type,
        file_size_bytes=path.stat().st_size,
    )

    indexed_chunks: list[IndexedChunk] = []
    user_id_str = str(user_id)
    document_id_str = str(document.id)
    for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
        payload = {
            "user_id": user_id_str,
            "document_id": document_id_str,
            "file_name": file_name,
            "chunk_index": idx,
            "content": chunk,
        }
        indexed_chunks.append(
            IndexedChunk(
                chunk_id=build_point_id(document_id=document_id_str, chunk_index=idx),
                content=chunk,
                vector=vector,
                payload=payload,
            )
        )

    upsert_document_chunks(indexed_chunks)

    return RAGIngestionResult(
        document_id=document_id_str,
        file_name=file_name,
        total_chunks=len(indexed_chunks),
        collection_name=settings.QDRANT_COLLECTION,
    )


def search_user_documents(
    user_id: str,
    query: str,
    top_k: int = 5,
    file_name: str | None = None,
) -> list[dict]:
    query_vector = embed_query(query)
    return search_user_chunks(
        query_vector=query_vector,
        user_id=user_id,
        top_k=top_k,
        file_name=file_name,
    )
