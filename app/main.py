from pathlib import Path
from uuid import UUID

from fastapi import Depends
from fastapi import FastAPI
from fastapi import File
from fastapi import HTTPException
from fastapi import Request
from fastapi import UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.coordinator import handle_user_question
from app.core.config import settings
from app.agent.sql_tool import get_enrolled_courses
from app.agent.sql_tool import get_last_transaction
from app.db.models import Transaction
from app.db.models import TransactionType
from app.db.models import User
from app.db.models import UserWallet
from app.db.session import SessionLocal
from app.db.session import get_db
from app.rag.service import ingest_user_document_bytes
from app.rag.service import ingest_user_document
from app.storage.gcs_storage import GCSStorage
from app.storage.gcs_storage import GCSStorageError


TOKEN_COST_PER_SUCCESS = 10
PROTECTED_PREFIXES = ("/api/agent", "/api/documents")
BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"
INDEX_FILE = TEMPLATES_DIR / "dashboard.html"

app = FastAPI(title="BIXSO Agentic Educator API", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
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


def _deduct_tokens_and_log_usage(user_uuid: UUID, path: str, method: str) -> bool:
    """
    Deduct token and append usage transaction in a single DB transaction.
    Returns True when deduction succeeds, False when wallet is missing/insufficient.
    """
    with SessionLocal() as db:
        wallet = db.scalar(
            select(UserWallet).where(UserWallet.user_id == user_uuid).with_for_update()
        )
        if not wallet or wallet.tokens_remaining < TOKEN_COST_PER_SUCCESS:
            db.rollback()
            return False

        wallet.tokens_remaining -= TOKEN_COST_PER_SUCCESS
        db.add(
            Transaction(
                user_id=user_uuid,
                type=TransactionType.USAGE,
                token_delta=-TOKEN_COST_PER_SUCCESS,
                description=f"Token guard deduction for {method} {path}",
            )
        )
        db.commit()
    return True


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
        _deduct_tokens_and_log_usage(
            user_uuid=user_uuid,
            path=request.url.path,
            method=request.method,
        )

    return response


@app.get("/", response_class=HTMLResponse)
def playground():
    if not INDEX_FILE.exists():
        return HTMLResponse(
            "<h2>Dashboard template not found.</h2>"
            "<p>Expected file: app/web/templates/dashboard.html</p>",
            status_code=500,
        )
    return FileResponse(INDEX_FILE)


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

    content = file.file.read()
    content_type = file.content_type or ("application/pdf" if suffix == ".pdf" else "text/plain")

    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    storage_path: str
    if settings.GCP_BUCKET_NAME:
        try:
            storage = GCSStorage()
            storage_path = storage.upload_bytes(
                data=content,
                user_id=str(user.id),
                file_name=file.filename,
                content_type=content_type,
            )
            result = ingest_user_document_bytes(
                session=db,
                user_id=str(user.id),
                file_name=file.filename,
                data=content,
                storage_path=storage_path,
                mime_type=content_type,
            )
        except GCSStorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    else:
        # Local fallback for development environments without GCP configuration.
        upload_root = Path("uploads") / str(user.id)
        upload_root.mkdir(parents=True, exist_ok=True)
        target = upload_root / file.filename
        target.write_bytes(content)
        storage_path = str(target.resolve())
        result = ingest_user_document(
            session=db,
            user_id=str(user.id),
            file_path=str(target),
        )

    db.commit()
    return {
        "message": "Document uploaded and indexed.",
        "storage_path": storage_path,
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
