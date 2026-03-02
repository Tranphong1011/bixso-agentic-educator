import argparse
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Course
from app.db.models import PlanType
from app.db.models import Transaction
from app.db.models import TransactionType
from app.db.models import User
from app.db.models import UserDocument
from app.db.models import UserWallet
from app.db.session import SessionLocal
from app.db.session import engine


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def _get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email))


def _get_course_by_code(session: Session, code: str) -> Course | None:
    return session.scalar(select(Course).where(Course.code == code))


def _ensure_user(session: Session, email: str, full_name: str, plan_type: PlanType) -> User:
    user = _get_user_by_email(session, email=email)
    if user:
        user.full_name = full_name
        user.plan_type = plan_type
        return user

    user = User(email=email, full_name=full_name, plan_type=plan_type)
    session.add(user)
    session.flush()
    return user


def _ensure_wallet(session: Session, user_id: Any, tokens_remaining: int) -> UserWallet:
    wallet = session.scalar(select(UserWallet).where(UserWallet.user_id == user_id))
    if wallet:
        wallet.tokens_remaining = tokens_remaining
        return wallet

    wallet = UserWallet(user_id=user_id, tokens_remaining=tokens_remaining)
    session.add(wallet)
    session.flush()
    return wallet


def _ensure_course(
    session: Session, code: str, title: str, description: str, token_cost: int
) -> Course:
    course = _get_course_by_code(session, code=code)
    if course:
        course.title = title
        course.description = description
        course.token_cost = token_cost
        return course

    course = Course(code=code, title=title, description=description, token_cost=token_cost)
    session.add(course)
    session.flush()
    return course


def _ensure_transaction(
    session: Session,
    user_id: Any,
    transaction_type: TransactionType,
    token_delta: int,
    description: str,
    course_id: Any | None = None,
) -> Transaction:
    existing = session.scalar(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.type == transaction_type,
            Transaction.token_delta == token_delta,
            Transaction.description == description,
            Transaction.course_id == course_id,
        )
    )
    if existing:
        return existing

    txn = Transaction(
        user_id=user_id,
        course_id=course_id,
        type=transaction_type,
        token_delta=token_delta,
        description=description,
    )
    session.add(txn)
    session.flush()
    return txn


def _ensure_document(
    session: Session,
    user_id: Any,
    file_name: str,
    storage_path: str,
    mime_type: str,
    file_size_bytes: int,
    qdrant_collection: str,
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
        existing.qdrant_collection = qdrant_collection
        return existing

    doc = UserDocument(
        user_id=user_id,
        file_name=file_name,
        storage_path=storage_path,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        qdrant_collection=qdrant_collection,
    )
    session.add(doc)
    session.flush()
    return doc


def seed_data(session: Session) -> None:
    user_a = _ensure_user(
        session,
        email="learner.a@example.com",
        full_name="Learner A",
        plan_type=PlanType.FREE,
    )
    user_b = _ensure_user(
        session,
        email="learner.b@example.com",
        full_name="Learner B",
        plan_type=PlanType.FREE,
    )

    _ensure_wallet(session, user_id=user_a.id, tokens_remaining=120)
    _ensure_wallet(session, user_id=user_b.id, tokens_remaining=5)

    course_phy = _ensure_course(
        session,
        code="PHY-101",
        title="Physics Fundamentals",
        description="Core mechanics and thermodynamics foundations.",
        token_cost=50,
    )
    _ensure_course(
        session,
        code="MTH-201",
        title="Calculus Basics",
        description="Limits, derivatives, and introductory integration.",
        token_cost=40,
    )
    _ensure_course(
        session,
        code="CS-105",
        title="Intro to Programming",
        description="Programming fundamentals with Python examples.",
        token_cost=30,
    )

    _ensure_transaction(
        session,
        user_id=user_a.id,
        transaction_type=TransactionType.TOPUP,
        token_delta=200,
        description="Initial top-up for account activation.",
    )
    _ensure_transaction(
        session,
        user_id=user_a.id,
        transaction_type=TransactionType.ENROLLMENT,
        token_delta=-50,
        description="Enrollment in Physics Fundamentals.",
        course_id=course_phy.id,
    )
    _ensure_transaction(
        session,
        user_id=user_a.id,
        transaction_type=TransactionType.USAGE,
        token_delta=-10,
        description="Agent response usage charge.",
    )

    _ensure_document(
        session,
        user_id=user_a.id,
        file_name="Physics_Notes.pdf",
        storage_path="uploads/learner-a/physics_notes.pdf",
        mime_type="application/pdf",
        file_size_bytes=245760,
        qdrant_collection="user_docs",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize PostgreSQL schema for BIXSO challenge.")
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed minimal sample data after creating tables.",
    )
    args = parser.parse_args()

    create_tables()
    print("Tables created successfully.")

    if args.seed:
        with SessionLocal() as session:
            seed_data(session)
            session.commit()
        print("Seed data applied successfully.")


if __name__ == "__main__":
    main()
