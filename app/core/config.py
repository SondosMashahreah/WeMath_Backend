
from datetime import timedelta
from functools import lru_cache
from io import BytesIO
from uuid import uuid4

from minio import Minio
from app.core.config import settings


BACKEND = settings.STORAGE_BACKEND.lower()

if BACKEND not in ("minio", "supabase"):
    raise ValueError("STORAGE_BACKEND must be minio or supabase")


# MinIO client is only created for local storage.
_client = (
    Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )
    if BACKEND == "minio"
    else None
)


@lru_cache(maxsize=1)
def supabase_bucket():
    from supabase import create_client

    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase Storage credentials are missing")

    client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
    )
    return client.storage.from_(settings.SUPABASE_STORAGE_BUCKET)


def ensure_bucket() -> None:
    if BACKEND == "minio":
        if not _client.bucket_exists(settings.MINIO_BUCKET):
            _client.make_bucket(settings.MINIO_BUCKET)
    # Supabase bucket is created once in the dashboard.


def _upload(object_name: str, data: bytes, content_type: str) -> str:
    if BACKEND == "supabase":
        supabase_bucket().upload(
            path=object_name,
            file=data,
            file_options={
                "content-type": content_type,
                "upsert": "false",
            },
        )
    else:
        ensure_bucket()
        _client.put_object(
            settings.MINIO_BUCKET,
            object_name,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    return object_name


def upload_avatar(user_id: int, data: bytes, content_type: str, extension: str) -> str:
    name = f"users/{user_id}/avatar-{uuid4().hex}.{extension}"
    return _upload(name, data, content_type)


def upload_research_file(
    user_id: int,
    submission_id: int,
    version: int,
    data: bytes,
    content_type: str,
    extension: str,
) -> str:
    name = (
        f"research/{user_id}/{submission_id}/"
        f"v{version}-{uuid4().hex}.{extension}"
    )
    return _upload(name, data, content_type)


def upload_certificate(user_id: int, data: bytes) -> str:
    name = f"certificates/{user_id}/{uuid4().hex}.pdf"
    return _upload(name, data, "application/pdf")


def delete_object(object_name: str | None) -> None:
    if not object_name:
        return

    try:
        if BACKEND == "supabase":
            supabase_bucket().remove([object_name])
        else:
            _client.remove_object(settings.MINIO_BUCKET, object_name)
    except Exception:
        # Preserve existing non-blocking delete behavior.
        pass


def _presigned_url(object_name: str | None) -> str | None:
    if not object_name:
        return None

    if BACKEND == "minio":
        return _client.presigned_get_object(
            settings.MINIO_BUCKET,
            object_name,
            expires=timedelta(hours=1),
        )

    result = supabase_bucket().create_signed_url(
        object_name,
        3600,
    )
    signed = result.get("signedURL") or result.get("signedUrl")

    if not signed:
        raise RuntimeError("Supabase did not return a signed URL")

    if signed.startswith(("https://", "http://")):
        return signed

    base = settings.SUPABASE_URL.rstrip("/")

    if signed.startswith("/storage/"):
        return base + signed
    if signed.startswith("/object/"):
        return base + "/storage/v1" + signed

    return base + "/storage/v1/" + signed.lstrip("/")


def presigned_avatar_url(object_name: str | None) -> str | None:
    return _presigned_url(object_name)


def presigned_file_url(object_name: str | None) -> str | None:
    return _presigned_url(object_name)
