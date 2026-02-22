import io
import logging
from datetime import timedelta

from minio import Minio

from app.config import settings

logger = logging.getLogger(__name__)

_client: Minio | None = None


def get_minio_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _client


def ensure_bucket() -> None:
    client = get_minio_client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
        logger.info("Created MinIO bucket '%s'", settings.minio_bucket)


def upload_file_bytes(object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload raw bytes to MinIO. Returns the object name."""
    client = get_minio_client()
    ensure_bucket()
    client.put_object(
        settings.minio_bucket,
        object_name,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    logger.info("Uploaded %s (%d bytes) to MinIO", object_name, len(data))
    return object_name


def get_presigned_url(object_name: str) -> str | None:
    if not object_name:
        return None
    try:
        client = get_minio_client()
        return client.presigned_get_object(
            settings.minio_bucket, object_name, expires=timedelta(hours=1)
        )
    except Exception:
        logger.exception("Failed to generate presigned URL for %s", object_name)
        return None
