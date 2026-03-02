from dataclasses import dataclass
from uuid import UUID

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.rag.service import search_user_documents
from app.rag.service import user_owns_document


@dataclass(frozen=True)
class RAGAnswer:
    answer: str
    sources: list[dict]
    retrieved_chunks: int


class RAGTool:
    def __init__(self, session: Session, llm_model: str = "gpt-4o-mini") -> None:
        self.session = session
        self.llm_model = llm_model

    def answer_question(
        self,
        user_id: str,
        question: str,
        file_name: str | None = None,
        top_k: int = 5,
    ) -> RAGAnswer:
        self._validate_user_id(user_id)
        if not question.strip():
            raise ValueError("Question must not be empty.")

        if file_name and not user_owns_document(self.session, user_id=user_id, file_name=file_name):
            return RAGAnswer(
                answer="The requested file does not belong to this user.",
                sources=[],
                retrieved_chunks=0,
            )

        chunks = search_user_documents(
            user_id=user_id,
            query=question,
            top_k=top_k,
            file_name=file_name,
        )
        if not chunks:
            return RAGAnswer(
                answer="I could not find relevant content in your uploaded documents.",
                sources=[],
                retrieved_chunks=0,
            )

        context, sources = self._build_context_and_sources(chunks)
        answer = self._generate_answer(question=question, context=context)
        return RAGAnswer(answer=answer, sources=sources, retrieved_chunks=len(chunks))

    def _validate_user_id(self, user_id: str) -> None:
        try:
            UUID(user_id)
        except ValueError as exc:
            raise ValueError("user_id must be a valid UUID.") from exc

    def _build_context_and_sources(self, chunks: list[dict]) -> tuple[str, list[dict]]:
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
        return "\n\n".join(context_blocks), sources

    def _generate_answer(self, question: str, context: str) -> str:
        if not settings.OPENAI_API_KEY:
            return f"Retrieved context (no LLM answer because OPENAI_API_KEY is missing):\n{context[:1000]}"

        prompt = (
            "You are an educational assistant.\n"
            "Use only the provided document context to answer.\n"
            "If context is insufficient, explicitly say what is missing.\n"
            "Give a concise explanation with 2-5 bullet points when possible."
        )
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        completion = client.chat.completions.create(
            model=self.llm_model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Question: {question}\n\nContext:\n{context}"},
            ],
        )
        return completion.choices[0].message.content or ""


def answer_from_user_documents(
    session: Session,
    user_id: str,
    question: str,
    file_name: str | None = None,
    top_k: int = 5,
) -> dict:
    result = RAGTool(session=session).answer_question(
        user_id=user_id,
        question=question,
        file_name=file_name,
        top_k=top_k,
    )
    return {"answer": result.answer, "sources": result.sources, "retrieved_chunks": result.retrieved_chunks}
