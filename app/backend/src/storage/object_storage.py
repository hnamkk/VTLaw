from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping
from urllib.parse import quote, urlparse

from src.core.config import settings


class ObjectStorageError(RuntimeError):
    """Raised when object storage is enabled but cannot complete an operation."""


@dataclass(frozen=True)
class ObjectMetadata:
    uri: str
    content_length: int | None
    content_type: str | None
    e_tag: str | None
    last_modified: object | None
    metadata: dict[str, str]


def is_object_uri(value: str | None) -> bool:
    return bool(value and value.startswith("s3://"))


def make_object_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key.lstrip('/')}"


def object_key_from_uri(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise ObjectStorageError("Invalid object storage URI.")
    return parsed.path.lstrip("/")


def build_legal_kb_object_key(
    *,
    kind: str,
    document_id: str,
    revision_id: str,
    sha256: str | None = None,
    asset_id: str | None = None,
    extension: str | None = None,
) -> str:
    ext = (extension or "").lstrip(".")
    if kind == "source":
        if not sha256:
            raise ObjectStorageError("kho văn bản source objects require sha256.")
        suffix = f".{ext}" if ext else ""
        return f"legal-kb/sources/{document_id}/{revision_id}/{sha256}/source{suffix}"
    if kind == "asset":
        if not asset_id:
            raise ObjectStorageError("kho văn bản asset objects require asset_id.")
        suffix = f".{ext}" if ext else ""
        return f"legal-kb/assets/{document_id}/{revision_id}/{asset_id}/original{suffix}"
    if kind == "rendition":
        suffix = f".{ext}" if ext else ""
        return f"legal-kb/renditions/{document_id}/{revision_id}/document{suffix}"
    raise ObjectStorageError(f"Unsupported kho văn bản object kind: {kind}")


class S3ObjectStorage:
    def __init__(self) -> None:
        if settings.OBJECT_STORAGE_PROVIDER != "s3":
            raise ObjectStorageError("Only S3-compatible object storage is supported.")
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - only happens with broken deploy deps
            raise ObjectStorageError("boto3 is required for S3 object storage.") from exc

        client_kwargs = {
            "aws_access_key_id": settings.S3_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.S3_SECRET_ACCESS_KEY,
            "region_name": settings.S3_REGION or "auto",
        }
        if settings.S3_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
        self._client = boto3.client("s3", **client_kwargs)
        self._bucket = settings.S3_BUCKET

    @property
    def bucket(self) -> str:
        return self._bucket

    def upload_file(
        self,
        source_path: Path,
        key: str,
        *,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> str:
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type
        if metadata:
            extra_args["Metadata"] = dict(metadata)
        kwargs = {"ExtraArgs": extra_args} if extra_args else {}
        self._client.upload_file(str(source_path), self._bucket, key, **kwargs)
        return make_object_uri(self._bucket, key)

    def delete_object(self, uri: str) -> None:
        key = object_key_from_uri(uri)
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def head_object(self, uri: str) -> ObjectMetadata:
        key = object_key_from_uri(uri)
        result = self._client.head_object(Bucket=self._bucket, Key=key)
        return ObjectMetadata(
            uri=uri,
            content_length=result.get("ContentLength"),
            content_type=result.get("ContentType"),
            e_tag=result.get("ETag"),
            last_modified=result.get("LastModified"),
            metadata=dict(result.get("Metadata") or {}),
        )

    def list_prefix(self, prefix: str, *, max_keys: int = 1000) -> list[str]:
        continuation_token = None
        uris: list[str] = []
        while True:
            params = {"Bucket": self._bucket, "Prefix": prefix, "MaxKeys": max_keys}
            if continuation_token:
                params["ContinuationToken"] = continuation_token
            result = self._client.list_objects_v2(**params)
            for item in result.get("Contents", []):
                key = item.get("Key")
                if key:
                    uris.append(make_object_uri(self._bucket, key))
            if not result.get("IsTruncated"):
                break
            continuation_token = result.get("NextContinuationToken")
            if not continuation_token:
                break
        return uris

    def public_or_presigned_url(self, uri: str, *, content_disposition: str | None = None) -> str:
        key = object_key_from_uri(uri)
        if settings.S3_PUBLIC_BASE_URL:
            base_url = settings.S3_PUBLIC_BASE_URL.rstrip("/")
            return f"{base_url}/{quote(key)}"

        params = {"Bucket": self._bucket, "Key": key}
        if content_disposition:
            params["ResponseContentDisposition"] = content_disposition
        return self._client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=settings.S3_PRESIGNED_URL_EXPIRE_SECONDS,
        )


@lru_cache
def get_object_storage() -> S3ObjectStorage:
    if not settings.OBJECT_STORAGE_ENABLED:
        raise ObjectStorageError("Object storage is disabled.")
    return S3ObjectStorage()
