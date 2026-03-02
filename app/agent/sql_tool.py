from uuid import UUID

from sqlalchemy import desc
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course
from app.db.models import Transaction
from app.db.models import TransactionType
from app.db.models import UserWallet


def get_wallet_balance(session: Session, user_id: str) -> int:
    wallet = session.scalar(select(UserWallet).where(UserWallet.user_id == UUID(user_id)))
    if not wallet:
        return 0
    return wallet.tokens_remaining


def get_last_transaction(session: Session, user_id: str) -> Transaction | None:
    return session.scalar(
        select(Transaction)
        .where(Transaction.user_id == UUID(user_id))
        .order_by(desc(Transaction.created_at))
        .limit(1)
    )


def get_enrolled_courses(session: Session, user_id: str) -> list[Course]:
    stmt = (
        select(Course)
        .join(Transaction, Transaction.course_id == Course.id)
        .where(
            Transaction.user_id == UUID(user_id),
            Transaction.type == TransactionType.ENROLLMENT,
        )
        .order_by(Course.title.asc())
    )
    return list(session.scalars(stmt).all())
