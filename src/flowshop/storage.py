"""One storage interface for product images and proof-of-payment files: a local folder or S3-compatible storage."""

import mimetypes
import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from flowshop.config import get_settings


class Storage(ABC):
    @abstractmethod
    def put(self, prefix: str, data: bytes, content_type: str) -> str: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @staticmethod
    def new_key(prefix: str, content_type: str) -> str:
        ext = mimetypes.guess_extension(content_type) or ".bin"
        return f"{prefix}/{uuid.uuid4().hex}{ext}"


class LocalStorage(Storage):
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("bad storage key")
        return path

    def put(self, prefix: str, data: bytes, content_type: str) -> str:
        key = self.new_key(prefix, content_type)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()


class S3Storage(Storage):
    """Works with AWS S3, Cloudflare R2, Google Cloud Storage interop and Azure via an S3 gateway."""

    def __init__(self, bucket: str, endpoint_url: str = "", region: str = ""):
        import boto3  # optional dependency: uv add boto3

        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url or None, region_name=region or None)

    def put(self, prefix: str, data: bytes, content_type: str) -> str:
        key = self.new_key(prefix, content_type)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()


@lru_cache
def get_storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "s3":
        return S3Storage(s.s3_bucket, s.s3_endpoint_url, s.s3_region)
    return LocalStorage(s.storage_dir)
