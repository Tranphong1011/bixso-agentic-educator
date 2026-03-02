from sqlalchemy.orm import Session

from app.agent.rag_tool import answer_from_user_documents
from app.agent.sql_tool import get_enrolled_courses
from app.agent.sql_tool import get_last_transaction
from app.agent.sql_tool import get_wallet_balance


def _is_rag_intent(question: str, file_name: str | None) -> bool:
    q = question.lower()
    rag_keywords = ["uploaded", "pdf", "document", "file", "notes", "based on my"]
    return bool(file_name) or any(k in q for k in rag_keywords)


def _is_sql_intent(question: str) -> bool:
    q = question.lower()
    sql_keywords = ["token", "balance", "transaction", "course", "enrolled", "quiz"]
    return any(k in q for k in sql_keywords)


def _handle_sql_question(session: Session, user_id: str, question: str) -> dict:
    q = question.lower()
    payload: dict = {"intent": "sql"}
    fragments: list[str] = []

    if "token" in q or "balance" in q or "enough" in q:
        tokens = get_wallet_balance(session, user_id)
        payload["tokens_remaining"] = tokens
        fragments.append(f"You currently have {tokens} tokens.")

    if "transaction" in q:
        last_tx = get_last_transaction(session, user_id)
        if last_tx:
            fragments.append(
                f"Your last transaction was type='{last_tx['type']}' with token_delta={last_tx['token_delta']}."
            )
            payload["last_transaction"] = {
                "type": last_tx["type"],
                "token_delta": last_tx["token_delta"],
                "description": last_tx["description"],
                "created_at": str(last_tx["created_at"]),
            }
        else:
            fragments.append("You do not have any transactions yet.")
            payload["last_transaction"] = None

    if "course" in q or "enrolled" in q:
        courses = get_enrolled_courses(session, user_id)
        payload["enrolled_courses"] = courses
        if courses:
            fragments.append(
                "Your enrolled courses are: "
                + ", ".join(f"{c['code']} ({c['title']})" for c in courses)
                + "."
            )
        else:
            fragments.append("You are not enrolled in any courses yet.")

    if not fragments:
        fragments.append("I can help with token balance, transactions, and enrolled courses.")

    payload["answer"] = " ".join(fragments)
    return payload


def handle_user_question(
    session: Session,
    user_id: str,
    question: str,
    file_name: str | None = None,
) -> dict:
    rag_intent = _is_rag_intent(question, file_name)
    sql_intent = _is_sql_intent(question)

    if rag_intent and not sql_intent:
        rag_result = answer_from_user_documents(user_id=user_id, question=question, file_name=file_name)
        return {
            "intent": "rag",
            "answer": rag_result["answer"],
            "sources": rag_result["sources"],
        }

    if sql_intent and not rag_intent:
        return _handle_sql_question(session=session, user_id=user_id, question=question)

    if sql_intent and rag_intent:
        sql_part = _handle_sql_question(session=session, user_id=user_id, question=question)
        rag_part = answer_from_user_documents(user_id=user_id, question=question, file_name=file_name)
        return {
            "intent": "hybrid",
            "answer": f"{sql_part['answer']}\n\nFrom your documents: {rag_part['answer']}",
            "sql": sql_part,
            "sources": rag_part["sources"],
        }

    return {
        "intent": "unknown",
        "answer": "I can help with wallet balance, transactions, enrolled courses, and uploaded documents.",
    }
