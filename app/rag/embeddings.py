from openai import OpenAI

from app.core.config import settings


def build_openai_client() -> OpenAI:
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required for embedding generation.")
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    client = build_openai_client()
    response = client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def embed_query(text: str) -> list[float]:
    vectors = embed_texts([text])
    return vectors[0]
