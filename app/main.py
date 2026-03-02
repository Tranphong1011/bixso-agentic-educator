from pathlib import Path
from uuid import UUID

from fastapi import Depends
from fastapi import FastAPI
from fastapi import File
from fastapi import HTTPException
from fastapi import Request
from fastapi import UploadFile
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.coordinator import handle_user_question
from app.agent.sql_tool import get_enrolled_courses
from app.agent.sql_tool import get_last_transaction
from app.db.models import Transaction
from app.db.models import TransactionType
from app.db.models import User
from app.db.models import UserWallet
from app.db.session import SessionLocal
from app.db.session import get_db
from app.rag.service import ingest_user_document


TOKEN_COST_PER_SUCCESS = 10
PROTECTED_PREFIXES = ("/api/agent", "/api/documents")

app = FastAPI(title="BIXSO Agentic Educator API", version="0.1.0")


class AskRequest(BaseModel):
    question: str
    file_name: str | None = None


def _extract_user_id(request: Request) -> str:
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-Id header.")
    try:
        UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="X-User-Id must be a valid UUID.") from exc
    return user_id


@app.middleware("http")
async def token_guard_middleware(request: Request, call_next):
    is_protected = any(request.url.path.startswith(prefix) for prefix in PROTECTED_PREFIXES)
    if not is_protected:
        return await call_next(request)

    user_id = request.headers.get("X-User-Id")
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Missing X-User-Id header."})

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "X-User-Id must be a valid UUID."})

    with SessionLocal() as db:
        wallet = db.scalar(select(UserWallet).where(UserWallet.user_id == user_uuid))
        if not wallet:
            return JSONResponse(status_code=404, content={"detail": "Wallet not found for this user."})
        if wallet.tokens_remaining < TOKEN_COST_PER_SUCCESS:
            return JSONResponse(
                status_code=402,
                content={"detail": "You need at least 10 tokens for each successful request. Please top up."},
            )

    response = await call_next(request)

    # Deduct only when response is successful.
    if response.status_code < 400:
        with SessionLocal() as db:
            wallet = db.scalar(select(UserWallet).where(UserWallet.user_id == user_uuid))
            if wallet:
                wallet.tokens_remaining -= TOKEN_COST_PER_SUCCESS
                db.add(
                    Transaction(
                        user_id=user_uuid,
                        type=TransactionType.USAGE,
                        token_delta=-TOKEN_COST_PER_SUCCESS,
                        description=f"Token guard deduction for {request.url.path}",
                    )
                )
                db.commit()

    return response


@app.get("/", response_class=HTMLResponse)
def playground() -> str:
    return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>BIXSO Agent Dashboard</title>
    <style>
      :root {
        --bg0: #f4f7fb;
        --bg1: #ffffff;
        --line: #d8e1ec;
        --text: #1e2a36;
        --muted: #60758a;
        --primary: #0d6e6e;
        --primary-hover: #095858;
        --ok: #0b8f56;
        --err: #be273a;
        --warn: #99610e;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        color: var(--text);
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        background:
          radial-gradient(circle at top right, #dff1f3 0, transparent 40%),
          radial-gradient(circle at bottom left, #f8efd9 0, transparent 35%),
          var(--bg0);
      }
      .container {
        max-width: 1100px;
        margin: 24px auto;
        padding: 0 16px 24px;
      }
      .hero {
        background: linear-gradient(130deg, #0d6e6e, #2e8484);
        color: #fff;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
      }
      .hero h1 { margin: 0 0 8px; font-size: 1.5rem; }
      .hero p { margin: 0; opacity: 0.92; }
      .grid {
        margin-top: 16px;
        display: grid;
        gap: 16px;
        grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      }
      .card {
        background: var(--bg1);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 16px;
        box-shadow: 0 4px 14px rgba(21, 36, 50, 0.06);
      }
      .card h3 { margin-top: 0; margin-bottom: 12px; }
      label { font-weight: 600; font-size: 0.92rem; }
      .hint { color: var(--muted); font-size: 0.85rem; margin-top: 6px; }
      input, textarea, button {
        width: 100%;
        margin-top: 8px;
        padding: 11px 12px;
        border-radius: 10px;
        border: 1px solid var(--line);
        font-size: 0.95rem;
      }
      textarea { min-height: 110px; resize: vertical; }
      button {
        background: var(--primary);
        color: #fff;
        border: 0;
        font-weight: 600;
        cursor: pointer;
        transition: background 0.15s ease;
      }
      button:hover { background: var(--primary-hover); }
      button:disabled { opacity: 0.65; cursor: wait; }
      .wallet {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-top: 10px;
      }
      .badge {
        border-radius: 999px;
        padding: 4px 10px;
        font-weight: 700;
        font-size: 0.85rem;
        border: 1px solid var(--line);
        background: #fff;
      }
      .ok { color: var(--ok); border-color: #bde6d3; background: #e9f7f0; }
      .err { color: var(--err); border-color: #f5cad1; background: #fcedf0; }
      .warn { color: var(--warn); border-color: #f3e0b9; background: #fcf6e7; }
      .response {
        margin-top: 16px;
      }
      pre {
        margin: 0;
        background: #0f1720;
        color: #d8e5f1;
        border-radius: 12px;
        padding: 14px;
        min-height: 180px;
        max-height: 420px;
        overflow: auto;
        font-size: 0.86rem;
      }
      .toast-wrap {
        position: fixed;
        right: 16px;
        top: 16px;
        width: min(380px, calc(100% - 32px));
        z-index: 999;
      }
      .toast {
        padding: 12px 14px;
        border-radius: 10px;
        margin-bottom: 8px;
        color: #fff;
        font-weight: 600;
        box-shadow: 0 8px 18px rgba(0, 0, 0, 0.14);
      }
      .toast.success { background: var(--ok); }
      .toast.error { background: var(--err); }
      .toast.info { background: #336eaa; }

      @media (max-width: 900px) {
        .container { margin: 16px auto; padding: 0 12px 20px; }
        .hero { padding: 16px; border-radius: 14px; }
        .hero h1 { font-size: 1.3rem; }
      }

      @media (max-width: 640px) {
        body { font-size: 14px; }
        .container { margin: 10px auto; padding: 0 10px 16px; }
        .hero p { font-size: 0.92rem; }
        .grid {
          grid-template-columns: 1fr;
          gap: 12px;
        }
        .card {
          padding: 12px;
          border-radius: 12px;
        }
        .card h3 { margin-bottom: 10px; font-size: 1rem; }
        input, textarea, button {
          font-size: 16px;
          padding: 10px;
        }
        .wallet {
          flex-wrap: wrap;
          gap: 8px;
        }
        pre {
          min-height: 140px;
          max-height: 320px;
          font-size: 0.8rem;
          padding: 10px;
        }
        .toast-wrap {
          right: 10px;
          top: 10px;
          width: calc(100% - 20px);
        }
      }
    </style>
  </head>
  <body>
    <div class="toast-wrap" id="toastWrap"></div>
    <div class="container">
      <div class="hero">
        <h1>BIXSO Agent Dashboard</h1>
        <p>
          All successful calls to <code>/api/agent/*</code> and <code>/api/documents/*</code> deduct 10 tokens.
          Wallet values below come directly from PostgreSQL (<code>user_wallets.tokens_remaining</code>).
        </p>
      </div>

      <div class="grid">
        <div class="card">
          <h3>User Context</h3>
          <label for="userId">User ID (X-User-Id)</label>
          <input id="userId" placeholder="69389f4a-0eef-415f-84f8-6b59ff1a9428" />
          <div class="hint">Every request uses this header to identify the current user.</div>
          <div class="wallet">
            <span class="badge" id="walletBadge">Tokens: -</span>
            <span class="badge warn" id="walletState">Unknown</span>
          </div>
          <button id="btnWallet" onclick="getWallet()">Get Wallet Balance</button>
          <button id="btnLastTx" onclick="getLastTransaction()">Get Last Transaction</button>
          <button id="btnCourses" onclick="getCourses()">Get Enrolled Courses</button>
        </div>

        <div class="card">
          <h3>Upload Document</h3>
          <label for="file">PDF/TXT File</label>
          <input id="file" type="file" accept=".pdf,.txt" />
          <div class="hint">This indexes chunks into Qdrant and updates <code>user_documents</code>.</div>
          <button id="btnUpload" onclick="uploadDoc()">Upload and Index</button>
        </div>

        <div class="card" style="grid-column: 1 / -1;">
          <h3>Ask Coordinator Agent</h3>
          <label for="question">Question</label>
          <textarea id="question" placeholder="How many tokens do I have left, and what was my last transaction?"></textarea>
          <label for="fileName">Optional file filter</label>
          <input id="fileName" placeholder="Physics_Notes.pdf" />
          <button id="btnAsk" onclick="askAgent()">Ask Agent</button>
        </div>
      </div>

      <div class="card response">
        <h3>API Response</h3>
        <pre id="out">{ "status": "Ready" }</pre>
      </div>
    </div>

    <script>
      function showToast(type, message) {
        const wrap = document.getElementById("toastWrap");
        const div = document.createElement("div");
        div.className = "toast " + type;
        div.textContent = message;
        wrap.appendChild(div);
        setTimeout(() => div.remove(), 3600);
      }

      function setOutput(data) {
        document.getElementById("out").textContent = JSON.stringify(data, null, 2);
      }

      function currentUserId() {
        return document.getElementById("userId").value.trim();
      }

      function headers(includeJson) {
        const h = { "X-User-Id": currentUserId() };
        if (includeJson) h["Content-Type"] = "application/json";
        return h;
      }

      function setLoading(buttonId, loading) {
        const btn = document.getElementById(buttonId);
        if (!btn) return;
        btn.disabled = loading;
        btn.dataset.prev = btn.dataset.prev || btn.textContent;
        btn.textContent = loading ? "Processing..." : btn.dataset.prev;
      }

      async function requestJson(url, options, buttonId) {
        if (!currentUserId()) {
          const message = "Please provide User ID first.";
          showToast("error", message);
          throw new Error(message);
        }
        setLoading(buttonId, true);
        try {
          const res = await fetch(url, options);
          const data = await res.json();
          setOutput(data);
          if (!res.ok) {
            const detail = data && data.detail ? data.detail : "Request failed";
            showToast("error", "Failed: " + detail);
            throw new Error(detail);
          }
          showToast("success", "Success: " + url);
          return data;
        } catch (err) {
          if (!(err instanceof Error)) {
            showToast("error", "Unexpected request failure.");
            throw err;
          }
          throw err;
        } finally {
          setLoading(buttonId, false);
        }
      }

      function updateWalletBadge(tokens) {
        const badge = document.getElementById("walletBadge");
        const state = document.getElementById("walletState");
        badge.textContent = "Tokens: " + tokens;
        state.className = "badge";
        if (tokens >= 30) {
          state.classList.add("ok");
          state.textContent = "Healthy";
        } else if (tokens >= 10) {
          state.classList.add("warn");
          state.textContent = "Low";
        } else {
          state.classList.add("err");
          state.textContent = "Insufficient";
        }
      }

      async function getWallet() {
        const data = await requestJson("/api/wallet", { headers: headers(false) }, "btnWallet");
        if (typeof data.tokens_remaining === "number") updateWalletBadge(data.tokens_remaining);
      }

      async function getLastTransaction() {
        await requestJson("/api/transactions/last", { headers: headers(false) }, "btnLastTx");
      }

      async function getCourses() {
        await requestJson("/api/courses/enrolled", { headers: headers(false) }, "btnCourses");
      }

      async function uploadDoc() {
        const f = document.getElementById("file").files[0];
        if (!f) {
          showToast("error", "Please choose a PDF/TXT file.");
          return;
        }
        const form = new FormData();
        form.append("file", f);
        await requestJson("/api/documents/upload", { method: "POST", headers: headers(false), body: form }, "btnUpload");
        await getWallet();
      }

      async function askAgent() {
        const question = document.getElementById("question").value.trim();
        if (!question) {
          showToast("error", "Question cannot be empty.");
          return;
        }
        const fileName = document.getElementById("fileName").value;
        const payload = { question: question, file_name: fileName || null };
        await requestJson("/api/agent/ask", {
          method: "POST",
          headers: headers(true),
          body: JSON.stringify(payload)
        }, "btnAsk");
        await getWallet();
      }

      showToast("info", "Dashboard ready. Enter user ID to start.");
    </script>
  </body>
</html>
"""


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/wallet")
def wallet_info(request: Request, db: Session = Depends(get_db)) -> dict:
    user_id = _extract_user_id(request)
    wallet = db.scalar(select(UserWallet).where(UserWallet.user_id == UUID(user_id)))
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found.")
    return {"user_id": user_id, "tokens_remaining": wallet.tokens_remaining}


@app.get("/api/transactions/last")
def last_transaction(request: Request, db: Session = Depends(get_db)) -> dict:
    user_id = _extract_user_id(request)
    tx = get_last_transaction(db, user_id)
    if not tx:
        return {"user_id": user_id, "last_transaction": None}
    return {
        "user_id": user_id,
        "last_transaction": {
            "type": tx["type"],
            "token_delta": tx["token_delta"],
            "description": tx["description"],
            "created_at": str(tx["created_at"]),
        },
    }


@app.get("/api/courses/enrolled")
def enrolled_courses(request: Request, db: Session = Depends(get_db)) -> dict:
    user_id = _extract_user_id(request)
    courses = get_enrolled_courses(db, user_id)
    return {"user_id": user_id, "courses": courses}


@app.post("/api/documents/upload")
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    user_id = _extract_user_id(request)
    user = db.scalar(select(User).where(User.id == UUID(user_id)))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".txt"}:
        raise HTTPException(status_code=400, detail="Only PDF/TXT files are supported.")

    upload_root = Path("uploads") / str(user.id)
    upload_root.mkdir(parents=True, exist_ok=True)
    target = upload_root / file.filename
    content = file.file.read()
    target.write_bytes(content)

    result = ingest_user_document(session=db, user_id=str(user.id), file_path=str(target))
    db.commit()
    return {
        "message": "Document uploaded and indexed.",
        "document_id": result.document_id,
        "file_name": result.file_name,
        "chunks": result.total_chunks,
        "collection": result.collection_name,
    }


@app.post("/api/agent/ask")
def ask_agent(
    request: Request,
    payload: AskRequest,
    db: Session = Depends(get_db),
) -> dict:
    user_id = _extract_user_id(request)
    user = db.scalar(select(User).where(User.id == UUID(user_id)))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    result = handle_user_question(
        session=db,
        user_id=user_id,
        question=payload.question,
        file_name=payload.file_name,
    )
    return {
        "user_id": user_id,
        "question": payload.question,
        "result": result,
    }
