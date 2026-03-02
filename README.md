# BIXSO Agentic Educator

Step 2 implementation for the BIXSO technical challenge using SQLAlchemy ORM and PostgreSQL.

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

3. Update `DATABASE_URL` in `.env`:

```env
DATABASE_URL=postgresql+psycopg2://postgres:########@localhost:5432/bixso_db
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
