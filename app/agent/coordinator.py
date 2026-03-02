from sqlalchemy.orm import Session

from app.agent.coordinator_graph import run_coordinator_graph


def handle_user_question(
    session: Session,
    user_id: str,
    question: str,
    file_name: str | None = None,
) -> dict:
    return run_coordinator_graph(
        session=session,
        user_id=user_id,
        question=question,
        file_name=file_name,
    )
