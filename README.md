# BIXSO Agentic Educator

FastAPI-based agentic educator with:
- PostgreSQL (users, wallets, transactions, courses, user_documents)
- Qdrant-based RAG
- LangGraph coordinator (SQL tool + RAG tool)
- Token guard (deduct 10 tokens on successful protected calls)
- Upload + indexing with optional GCP Cloud Storage

## 1. Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

Set required values in `.env`:
- `DATABASE_URL`
- `OPENAI_API_KEY`
- `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`

Optional (recommended for production uploads):
- `GCP_PROJECT_ID`
- `GCP_BUCKET_NAME`
- `GCP_SERVICE_ACCOUNT_KEY_PATH` or `GCP_SERVICE_ACCOUNT_JSON`

## 2. Initialize database

```bash
python -m app.db.init_db
python -m app.db.init_db --seed
```

## 3. Run API

```bash
uvicorn app.main:app --reload
```

Open:
- `http://127.0.0.1:8000/`

## 4. Upload storage behavior

- If `GCP_BUCKET_NAME` is set:
  - Uploads go to GCS.
  - `storage_path` in DB is `gs://...`.
  - Upload errors return HTTP 500 with explicit storage message.
- If `GCP_BUCKET_NAME` is empty:
  - Fallback to local `uploads/` directory (dev only).

## 5. Core protected endpoints

- `POST /api/documents/upload`
- `POST /api/agent/ask`

Token guard:
- Requires at least 10 tokens before protected calls.
- Deducts 10 only when response is successful.
- Logs `transactions(type=usage, token_delta=-10)`.

## 6. Deploy on Render

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set env vars in Render service (same as `.env`).

For production, use:
- Render PostgreSQL Internal URL for `DATABASE_URL`
- GCS for uploads 
