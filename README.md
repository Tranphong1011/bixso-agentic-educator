# BIXSO Agentic Educator

Step 2-3 implementation for the BIXSO technical challenge using SQLAlchemy ORM, PostgreSQL, OpenAI embeddings, and Qdrant.

## Prerequisites

- Python 3.10+
- PostgreSQL running locally or remotely
- A created database (example: `bixso_db`)

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create your environment file:

```bash
cp .env.example .env
```

3. Update `.env`:

```env
DATABASE_URL=postgresql+psycopg2://postgres:########@localhost:5432/bixso_db
OPENAI_API_KEY=###############3
EMBEDDING_MODEL=text-embedding-3-small
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=education-collection
CHUNK_SIZE=800
CHUNK_OVERLAP=120
```

## Initialize DB schema

Create tables only:

```bash
python -m app.db.init_db
```

Create tables and seed minimal sample data:

```bash
python -m app.db.init_db --seed
```

This script is idempotent for sample users/courses/documents/transactions and can be run multiple times.

## Step 3: Vector store (Qdrant) + document indexing

Supported file types:

- `.pdf`
- `.txt`

Index a document for a user by email:

```bash
python -m app.rag.index_document --user-email learner.a@example.com --file-path ./data/Physics_Notes.pdf
```

Index a document by user UUID:

```bash
python -m app.rag.index_document --user-id <user_uuid> --file-path ./data/Physics_Notes.pdf
```

Search indexed chunks (user-scoped):

```bash
python -m app.rag.query_document --user-id <user_uuid> --query "Second Law of Thermodynamics" --top-k 5 --file-name Physics_Notes.pdf
```

What this does:

- Reads PDF/TXT content.
- Splits text into chunks (`CHUNK_SIZE`, `CHUNK_OVERLAP`).
- Generates embeddings with OpenAI (`EMBEDDING_MODEL`).
- Upserts vectors to Qdrant collection (`QDRANT_COLLECTION`).
- Stores/updates document metadata in PostgreSQL table `user_documents`.

## Included tables

- `users`
- `user_wallets`
- `transactions`
- `courses`
- `user_documents`

## Quick SQL checks

```sql
SELECT id, email, full_name, plan_type FROM users;
SELECT user_id, tokens_remaining FROM user_wallets;
SELECT user_id, type, token_delta, created_at FROM transactions ORDER BY created_at DESC;
SELECT user_id, file_name, qdrant_collection FROM user_documents;
```

## Notes

- This step uses `Base.metadata.create_all(...)` (no Alembic yet).
- `transactions` represents token top-up, usage, and enrollment history.
- `user_documents` stores RAG metadata and is ready for user-scoped filtering in later steps.
