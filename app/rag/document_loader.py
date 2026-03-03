from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".pdf", ".txt"}


def load_document_text(file_path: str) -> tuple[str, str]:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Unsupported file type. Only .pdf and .txt are supported.")

    if extension == ".txt":
        return path.read_text(encoding="utf-8"), "text/plain"

    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages), "application/pdf"


def load_document_text_from_bytes(
    data: bytes,
    file_name: str,
    mime_type: str | None = None,
) -> tuple[str, str]:
    if not data:
        raise ValueError("Empty document data.")

    extension = Path(file_name).suffix.lower()
    resolved_mime = mime_type or ("application/pdf" if extension == ".pdf" else "text/plain")
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Unsupported file type. Only .pdf and .txt are supported.")

    if extension == ".txt":
        return data.decode("utf-8"), "text/plain"

    reader = PdfReader(BytesIO(data))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages), "application/pdf"
