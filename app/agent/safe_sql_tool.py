import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


class SafeSQLTool:
    """
    Guarded SQL executor:
    - Only allows SELECT/CTE SELECT.
    - Blocks destructive keywords.
    - Enforces user scoping for sensitive tables.
    """

    _FORBIDDEN_PATTERN = re.compile(
        r"\b(DELETE|UPDATE|DROP|INSERT|ALTER|TRUNCATE|CREATE|GRANT|REVOKE)\b",
        re.IGNORECASE,
    )
    _FROM_JOIN_PATTERN = re.compile(
        r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        re.IGNORECASE,
    )
    _USER_ID_SCOPE_PATTERN = re.compile(
        r"\buser_id\s*=\s*:user_id\b",
        re.IGNORECASE,
    )
    _USERS_ID_SCOPE_PATTERN = re.compile(
        r"\b(?:users\.)?id\s*=\s*:user_id\b",
        re.IGNORECASE,
    )
    _ALLOWED_START_PATTERN = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)

    _SENSITIVE_TABLES = {"transactions", "user_wallets", "user_documents", "users"}

    def __init__(self, session: Session) -> None:
        self.session = session

    def execute_select(self, sql: str, user_id: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self._validate_user_id(user_id)
        cleaned_sql = sql.strip()
        self._validate_sql(cleaned_sql)
        self._enforce_user_scope(cleaned_sql)

        bind_params = dict(params or {})
        bind_params["user_id"] = user_id

        result = self.session.execute(text(cleaned_sql), bind_params)
        return [dict(row._mapping) for row in result]

    def _validate_user_id(self, user_id: str) -> None:
        try:
            UUID(user_id)
        except ValueError as exc:
            raise ValueError("user_id must be a valid UUID.") from exc

    def _validate_sql(self, sql: str) -> None:
        if not self._ALLOWED_START_PATTERN.match(sql):
            raise ValueError("Only SELECT queries are allowed.")
        if self._FORBIDDEN_PATTERN.search(sql):
            raise ValueError("Destructive SQL is not allowed.")

        # Disallow multi-statement execution; allow a single optional trailing semicolon.
        stripped = sql.rstrip()
        if ";" in stripped[:-1]:
            raise ValueError("Only a single SQL statement is allowed.")

    def _enforce_user_scope(self, sql: str) -> None:
        referenced_tables = {name.lower() for name in self._FROM_JOIN_PATTERN.findall(sql)}
        touches_sensitive = bool(self._SENSITIVE_TABLES.intersection(referenced_tables))
        if not touches_sensitive:
            return

        has_user_id_scope = bool(self._USER_ID_SCOPE_PATTERN.search(sql))
        has_users_scope = bool(self._USERS_ID_SCOPE_PATTERN.search(sql))
        if not (has_user_id_scope or has_users_scope):
            raise ValueError(
                "Query touches user data and must include user scope: "
                "`user_id = :user_id` (or `users.id = :user_id`)."
            )
