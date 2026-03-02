from sqlalchemy.orm import Session

from app.agent.safe_sql_tool import SafeSQLTool


def get_wallet_balance(session: Session, user_id: str) -> int:
    sql = """
    SELECT tokens_remaining
    FROM user_wallets
    WHERE user_id = :user_id
    LIMIT 1
    """
    rows = SafeSQLTool(session).execute_select(sql=sql, user_id=user_id)
    if not rows:
        return 0
    return int(rows[0]["tokens_remaining"])


def get_last_transaction(session: Session, user_id: str) -> dict | None:
    sql = """
    SELECT type, token_delta, description, created_at
    FROM transactions
    WHERE user_id = :user_id
    ORDER BY created_at DESC
    LIMIT 1
    """
    rows = SafeSQLTool(session).execute_select(sql=sql, user_id=user_id)
    if not rows:
        return None
    return rows[0]


def get_enrolled_courses(session: Session, user_id: str) -> list[dict]:
    sql = """
    SELECT c.code, c.title, c.token_cost
    FROM courses c
    JOIN transactions t ON t.course_id = c.id
    WHERE t.user_id = :user_id
      AND t.type = :tx_type
    ORDER BY c.title ASC
    """
    rows = SafeSQLTool(session).execute_select(
        sql=sql,
        user_id=user_id,
        params={"tx_type": "ENROLLMENT"},
    )
    return rows
