import argparse

from app.db.session import SessionLocal
from app.rag.service import get_user_by_email
from app.rag.service import get_user_by_id
from app.rag.service import ingest_user_document


def main() -> None:
    parser = argparse.ArgumentParser(description="Index a user PDF/TXT into Qdrant.")
    user_group = parser.add_mutually_exclusive_group(required=True)
    user_group.add_argument("--user-id", type=str, help="User UUID in the database")
    user_group.add_argument("--user-email", type=str, help="User email in the database")
    parser.add_argument("--file-path", type=str, required=True, help="Path to .pdf or .txt file")
    args = parser.parse_args()

    with SessionLocal() as session:
        if args.user_id:
            user = get_user_by_id(session, args.user_id)
        else:
            user = get_user_by_email(session, args.user_email)

        if not user:
            raise ValueError("User not found. Please provide a valid user id or email.")

        result = ingest_user_document(
            session=session,
            user_id=str(user.id),
            file_path=args.file_path,
        )
        session.commit()

    print("Document indexed successfully.")
    print(f"user_id={user.id}")
    print(f"document_id={result.document_id}")
    print(f"file_name={result.file_name}")
    print(f"chunks={result.total_chunks}")
    print(f"collection={result.collection_name}")


if __name__ == "__main__":
    main()
