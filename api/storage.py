"""
api/storage.py — Abstract storage backend for file I/O.

Switch between local filesystem (dev) and S3/R2 (prod) via env var:
    STORAGE_BACKEND=local  (default)
    STORAGE_BACKEND=s3

S3 env vars (when STORAGE_BACKEND=s3):
    S3_BUCKET_NAME          — required
    S3_REGION               — default: us-east-1
    S3_ENDPOINT_URL         — optional (for R2: https://<account>.r2.cloudflarestorage.com)
    AWS_ACCESS_KEY_ID       — required
    AWS_SECRET_ACCESS_KEY   — required
    S3_PUBLIC_URL_PREFIX    — optional CDN prefix (e.g. https://cdn.labx.app)
                              if omitted, generates presigned URLs (1h TTL)
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger("labx.storage")

_BASE_DIR = Path(__file__).resolve().parent.parent


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes) -> str:
        """Persist bytes under `key`. Returns the storage key (may differ for normalisation)."""

    @abstractmethod
    def load(self, key: str) -> bytes:
        """Return bytes for `key`. Raises FileNotFoundError if missing."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove object at `key`. No-op if already absent."""

    @abstractmethod
    def url(self, key: str) -> str:
        """Return a URL that serves the object to the client."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """True if the object exists in the backend."""


# ─────────────────────────────────────────────────────────────────
# Local filesystem backend (default — dev + single-instance prod)
# ─────────────────────────────────────────────────────────────────

class LocalStorage(StorageBackend):
    """Stores files on the local filesystem under BASE_DIR/data/<prefix>/."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self._base = Path(base_dir) if base_dir else _BASE_DIR / "data"
        self._base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self._base / key).resolve()
        if not str(p).startswith(str(self._base)):
            raise ValueError(f"Path traversal detected: {key!r}")
        return p

    def save(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.debug("LocalStorage.save key=%s bytes=%d", key, len(data))
        return key

    def load(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(f"No such file in storage: {key!r}")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()
            logger.debug("LocalStorage.delete key=%s", key)

    def url(self, key: str) -> str:
        app_url = os.getenv("APP_URL", "http://localhost:8000")
        return f"{app_url}/api/storage/{key}"

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).exists()
        except ValueError:
            return False


# ─────────────────────────────────────────────────────────────────
# S3 / Cloudflare R2 backend (multi-instance prod)
# ─────────────────────────────────────────────────────────────────

class S3Storage(StorageBackend):
    """Stores files in S3-compatible object storage (AWS S3 or Cloudflare R2)."""

    def __init__(
        self,
        bucket: str,
        region:       str = "us-east-1",
        endpoint_url: str | None = None,
        public_url_prefix: str | None = None,
        presign_ttl:  int = 3600,
    ) -> None:
        self._bucket       = bucket
        self._region       = region
        self._endpoint_url = endpoint_url
        self._public_prefix = public_url_prefix.rstrip("/") if public_url_prefix else None
        self._presign_ttl  = presign_ttl
        self._client       = self._make_client()

    def _make_client(self):
        try:
            import boto3  # type: ignore
            kwargs: dict = dict(region_name=self._region)
            if self._endpoint_url:
                kwargs["endpoint_url"] = self._endpoint_url
            return boto3.client("s3", **kwargs)
        except ImportError:
            raise RuntimeError("boto3 is required for S3 storage — pip install boto3")

    def save(self, key: str, data: bytes) -> str:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        logger.debug("S3Storage.save bucket=%s key=%s bytes=%d", self._bucket, key, len(data))
        return key

    def load(self, key: str) -> bytes:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            return resp["Body"].read()
        except Exception as e:
            if "NoSuchKey" in str(type(e).__name__) or "404" in str(e):
                raise FileNotFoundError(f"No such object in S3: {key!r}")
            raise

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
        logger.debug("S3Storage.delete bucket=%s key=%s", self._bucket, key)

    def url(self, key: str) -> str:
        if self._public_prefix:
            return f"{self._public_prefix}/{key}"
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=self._presign_ttl,
        )

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False


# ─────────────────────────────────────────────────────────────────
# Factory — returns configured backend singleton
# ─────────────────────────────────────────────────────────────────

def get_storage() -> StorageBackend:
    """Return storage backend based on STORAGE_BACKEND env var."""
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    if backend == "s3":
        bucket = os.getenv("S3_BUCKET_NAME", "")
        if not bucket:
            raise RuntimeError("S3_BUCKET_NAME must be set when STORAGE_BACKEND=s3")
        return S3Storage(
            bucket           = bucket,
            region           = os.getenv("S3_REGION", "us-east-1"),
            endpoint_url     = os.getenv("S3_ENDPOINT_URL") or None,
            public_url_prefix= os.getenv("S3_PUBLIC_URL_PREFIX") or None,
            presign_ttl      = int(os.getenv("S3_PRESIGN_TTL", "3600")),
        )
    return LocalStorage()


# Module-level singleton — import and use directly:
#   from .storage import storage
#   storage.save("activity_photos/abc.jpg", data)
storage: StorageBackend = get_storage()
