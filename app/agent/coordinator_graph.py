from typing import Any
from typing import Literal
from typing import TypedDict

from langgraph.graph import END
from langgraph.graph import START
from langgraph.graph import StateGraph
from sqlalchemy.orm import Session

from app.agent.rag_tool import answer_from_user_documents
from app.agent.sql_tool import get_enrolled_courses
from app.agent.sql_tool import get_last_transaction
from app.agent.sql_tool import get_wallet_balance


Intent = Literal["sql", "rag", "hybrid", "unknown"]


class AgentState(TypedDict, total=False):
    session: Session
    user_id: str
    question: str
    file_name: str | None
    intent: Intent
    result: dict[str, Any]


def detect_intent(question: str, file_name: str | None) -> Intent:
    q = question.lower()
    rag_keywords = ["uploaded", "pdf", "document", "file", "notes", "based on my"]
    sql_keywords = ["token", "balance", "transaction", "course", "enrolled", "quiz"]

    rag_intent = bool(file_name) or any(k in q for k in rag_keywords)
    sql_intent = any(k in q for k in sql_keywords)

    if sql_intent and rag_intent:
        return "hybrid"
    if sql_intent:
        return "sql"
    if rag_intent:
        return "rag"
    return "unknown"


def route_node(state: AgentState) -> AgentState:
    return {"intent": detect_intent(state["question"], state.get("file_name"))}


def sql_tool_node(state: AgentState) -> AgentState:
    session = state["session"]
    user_id = state["user_id"]
    q = state["question"].lower()
    payload: dict[str, Any] = {"intent": "sql"}
    fragments: list[str] = []

    if "token" in q or "balance" in q or "enough" in q:
        tokens = get_wallet_balance(session, user_id)
        payload["tokens_remaining"] = tokens
        fragments.append(f"You currently have {tokens} tokens.")

    if "transaction" in q:
        last_tx = get_last_transaction(session, user_id)
        if last_tx:
            payload["last_transaction"] = {
                "type": last_tx["type"],
                "token_delta": last_tx["token_delta"],
                "description": last_tx["description"],
                "created_at": str(last_tx["created_at"]),
            }
            fragments.append(
                f"Your last transaction was type='{last_tx['type']}' with token_delta={last_tx['token_delta']}."
            )
        else:
            payload["last_transaction"] = None
            fragments.append("You do not have any transactions yet.")

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
    return {"result": payload}


def rag_tool_node(state: AgentState) -> AgentState:
    session = state["session"]
    result = answer_from_user_documents(
        session=session,
        user_id=state["user_id"],
        question=state["question"],
        file_name=state.get("file_name"),
    )
    return {
        "result": {
            "intent": "rag",
            "answer": result["answer"],
            "sources": result["sources"],
            "retrieved_chunks": result.get("retrieved_chunks", 0),
        }
    }


def hybrid_tool_node(state: AgentState) -> AgentState:
    sql_result = sql_tool_node(state)["result"]
    rag_result = rag_tool_node(state)["result"]
    return {
        "result": {
            "intent": "hybrid",
            "answer": f"{sql_result['answer']}\n\nFrom your documents: {rag_result['answer']}",
            "sql": sql_result,
            "sources": rag_result.get("sources", []),
            "retrieved_chunks": rag_result.get("retrieved_chunks", 0),
        }
    }


def unknown_tool_node(state: AgentState) -> AgentState:
    return {
        "result": {
            "intent": "unknown",
            "answer": "I can help with wallet balance, transactions, enrolled courses, and uploaded documents.",
        }
    }


def _route_by_intent(state: AgentState) -> str:
    return state["intent"]


def build_coordinator_graph():
    graph = StateGraph(AgentState)
    graph.add_node("route", route_node)
    graph.add_node("sql_tool", sql_tool_node)
    graph.add_node("rag_tool", rag_tool_node)
    graph.add_node("hybrid_tool", hybrid_tool_node)
    graph.add_node("unknown_tool", unknown_tool_node)

    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route",
        _route_by_intent,
        {
            "sql": "sql_tool",
            "rag": "rag_tool",
            "hybrid": "hybrid_tool",
            "unknown": "unknown_tool",
        },
    )
    graph.add_edge("sql_tool", END)
    graph.add_edge("rag_tool", END)
    graph.add_edge("hybrid_tool", END)
    graph.add_edge("unknown_tool", END)
    return graph.compile()


COORDINATOR_GRAPH = build_coordinator_graph()


def run_coordinator_graph(
    session: Session,
    user_id: str,
    question: str,
    file_name: str | None = None,
) -> dict[str, Any]:
    state: AgentState = {
        "session": session,
        "user_id": user_id,
        "question": question,
        "file_name": file_name,
    }
    final_state = COORDINATOR_GRAPH.invoke(state)
    return final_state["result"]
