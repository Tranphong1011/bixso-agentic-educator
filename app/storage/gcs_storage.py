import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from google.cloud import storage
from google.oauth2 import service_account

from app.core.config import settings


class GCSStorageError(Exception):
    pass


class GCSStorage:
    def __init__(self) -> None:
        if not settings.GCP_BUCKET_NAME:
            raise GCSStorageError("GCP_BUCKET_NAME is required.")
        self.bucket_name = settings.GCP_BUCKET_NAME
        self.client = self._build_client()
        self.bucket = self.client.bucket(self.bucket_name)

    def _build_client(self) -> storage.Client:
        if settings.GCP_SERVICE_ACCOUNT_JSON:
            info = json.loads(settings.GCP_SERVICE_ACCOUNT_JSON)
            credentials = service_account.Credentials.from_service_account_info(info)
            return storage.Client(project=settings.GCP_PROJECT_ID or info.get("project_id"), credentials=credentials)

        if settings.GCP_SERVICE_ACCOUNT_KEY_PATH:
            key_path = Path(settings.GCP_SERVICE_ACCOUNT_KEY_PATH).resolve()
            if not key_path.exists():
                raise GCSStorageError(f"GCP service account key file not found: {key_path}")
            credentials = service_account.Credentials.from_service_account_file(str(key_path))
            return storage.Client(project=settings.GCP_PROJECT_ID or credentials.project_id, credentials=credentials)

        # Fallback to ADC (for runtime environments with workload identity).
        return storage.Client(project=settings.GCP_PROJECT_ID or None)

    def upload_bytes(
        self,
        data: bytes,
        user_id: str,
        file_name: str,
        content_type: str | None = None,
    ) -> str:
        if not data:
            raise GCSStorageError("Cannot upload empty file.")

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        object_name = f"user-documents/{user_id}/{timestamp}-{uuid4().hex}-{file_name}"
        blob = self.bucket.blob(object_name)
        try:
            blob.upload_from_file(BytesIO(data), size=len(data), content_type=content_type)
        except Exception as exc:  # pragma: no cover - external SDK failure path
            raise GCSStorageError(f"Failed to upload file to GCS: {exc}") from exc
        return f"gs://{self.bucket_name}/{object_name}"
