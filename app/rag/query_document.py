import argparse
import json

from app.rag.service import search_user_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Search indexed chunks in Qdrant for a user.")
    parser.add_argument("--user-id", type=str, required=True, help="User UUID")
    parser.add_argument("--query", type=str, required=True, help="Search query")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to return")
    parser.add_argument("--file-name", type=str, default=None, help="Optional file name filter")
    args = parser.parse_args()

    results = search_user_documents(
        user_id=args.user_id,
        query=args.query,
        top_k=args.top_k,
        file_name=args.file_name,
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
