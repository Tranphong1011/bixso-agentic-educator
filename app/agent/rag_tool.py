from openai import OpenAI

from app.core.config import settings
from app.rag.service import search_user_documents


def answer_from_user_documents(
    user_id: str,
    question: str,
    file_name: str | None = None,
    top_k: int = 5,
) -> dict:
    chunks = search_user_documents(
        user_id=user_id,
        query=question,
        top_k=top_k,
        file_name=file_name,
    )
    if not chunks:
        return {
            "answer": "I could not find relevant content in your uploaded documents.",
            "sources": [],
        }

    context_blocks: list[str] = []
    sources: list[dict] = []
    for item in chunks:
        payload = item.get("payload", {})
        context_blocks.append(payload.get("content", ""))
        sources.append(
            {
                "file_name": payload.get("file_name"),
                "chunk_index": payload.get("chunk_index"),
                "score": item.get("score"),
            }
        )

    context = "\n\n".join(context_blocks)
    if not settings.OPENAI_API_KEY:
        # Safe fallback when key is not configured.
        return {
            "answer": f"Retrieved context (no LLM answer because OPENAI_API_KEY is missing):\n{context[:1000]}",
            "sources": sources,
        }

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an educational assistant. Answer only from the provided context. "
                    "If context is insufficient, say so clearly."
                ),
            },
            {
                "role": "user",
                "content": f"Question: {question}\n\nContext:\n{context}",
            },
        ],
    )

    return {
        "answer": completion.choices[0].message.content or "",
        "sources": sources,
    }
