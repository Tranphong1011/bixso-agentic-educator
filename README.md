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
.europe-west3-0.gcp.cloud.qdrant.io
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

## Step 4: FastAPI API + Token Guard

Run the API:

```bash
uvicorn app.main:app --reload
```

Open UI playground:

- `http://127.0.0.1:8000/`

Use header for protected endpoints:

- `X-User-Id: <user_uuid>`

Protected endpoints (Token Guard applies, costs 10 tokens on success):

- `POST /api/documents/upload`
- `POST /api/agent/ask`

Utility endpoints:

- `GET /api/health`
- `GET /api/wallet`
- `GET /api/transactions/last`
- `GET /api/courses/enrolled`

Token Guard behavior:

- Rejects request if user has fewer than 10 tokens.
- Deducts 10 tokens only after successful protected response.
- Writes usage transaction (`type=usage`, `token_delta=-10`).

## Step 5: Safe SQL Tool (SELECT-only)

Implemented in:

- `app/agent/safe_sql_tool.py`
- `app/agent/sql_tool.py`

Behavior:

- Only allows `SELECT` (including CTE `WITH ... SELECT`).
- Blocks destructive SQL keywords (`DELETE`, `UPDATE`, `DROP`, `INSERT`, `ALTER`, `TRUNCATE`, `CREATE`, ...).
- Blocks multi-statement SQL execution.
- Enforces user scoping on sensitive tables:
  - requires `user_id = :user_id` (or `users.id = :user_id`) in query.

Current SQL access for wallet/transactions/enrollments is routed through this tool.

## Step 6: RAG Tool

Implemented in:

- `app/agent/rag_tool.py` (`RAGTool`)
- `app/rag/service.py`
- `app/rag/vector_store.py`

RAG flow:

1. Receive user question and optional `file_name`.
2. Validate `user_id` and (if provided) verify the file belongs to that user in `user_documents`.
3. Query Qdrant with a strict filter: `payload.user_id == <request_user_id>`.
4. Retrieve nearest chunks, build context prompt, and call LLM (`gpt-4o-mini`) to generate answer.

Security note:

- The tool never queries cross-user documents because both metadata ownership check and Qdrant `user_id` filter are enforced.

## Step 7: Coordinator Agent with LangGraph Router

Implemented in:

- `app/agent/coordinator_graph.py`
- `app/agent/coordinator.py`

Architecture:

- `route` node detects intent from user question (`sql`, `rag`, `hybrid`, `unknown`).
- `sql_tool` node executes SQL Tool flows (wallet, last transaction, enrolled courses).
- `rag_tool` node executes RAG Tool flow.
- `hybrid_tool` node combines SQL + RAG outputs.

Routing rules:

- Token/balance/transaction/course/enrollment questions -> SQL Tool.
- Uploaded document/PDF/notes questions -> RAG Tool.
- Mixed questions -> Hybrid route.

## Step 8: Token Guard + Usage Business Logic

Implemented in:

- `app/main.py` (`token_guard_middleware`)

Behavior:

- Middleware checks wallet before protected calls (`/api/agent/*`, `/api/documents/*`).
- Requires at least 10 tokens before processing.
- Deducts tokens only when response is successful (`status < 400`).
- Deduction and usage logging are atomic (single DB transaction + wallet row lock).
- Every deduction creates a `transactions` record with:
  - `type = usage`
  - `token_delta = -10`
  - request path/method in description

## UI structure (maintainable)

- `app/web/templates/dashboard.html`
- `app/web/static/css/dashboard.css`
- `app/web/static/js/dashboard.js`

`/` serves the HTML template and static assets are served from `/static/*`.

## Deploy notes (Render)

Recommended start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Practical notes before deploy:

- Do not hardcode localhost ports in production.
- `uploads/` is local filesystem; on Render it is ephemeral. Use object storage (S3/GCS) for persistence.
- Ensure required env vars exist (`DATABASE_URL`, `OPENAI_API_KEY`, `QDRANT_*`).

If local page keeps loading forever, check port conflict:

```powershell
netstat -ano | Select-String ':8000'
Get-Process -Id <pid>
Stop-Process -Id <pid> -Force
```

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
