"""Kho đối tượng S3 (MinIO / RustFS) cho giáo trình và ghi âm. Chủ: Long (C2-08).

Địa chỉ trả về dạng `s3://{bucket}/{key}` – lưu vào `syllabus_documents.file_url`; worker (C1-09) đọc lại bằng
`ObjectStorage.get(url)`. Bucket `S3_BUCKET` chưa có thì tự tạo ở lần ghi đầu tiên.
"""

import io
import threading
from functools import lru_cache
from typing import Protocol
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error
from urllib3.exceptions import HTTPError

from app.core.config import get_settings


class StorageUnavailable(Exception):
    """Không ghi / đọc được kho đối tượng (mất kết nối, sai khóa…)."""


def _split(url: str) -> tuple[str, str]:
    p = urlparse(url)
    if p.scheme != "s3" or not p.netloc or not p.path.lstrip("/"):
        raise ValueError(f"địa chỉ kho đối tượng không hợp lệ: {url!r}")
    return p.netloc, p.path.lstrip("/")


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> str: ...
    def get(self, url: str) -> bytes: ...
    def remove(self, url: str) -> None: ...


class InMemoryStorage:
    """Bản trong bộ nhớ cho test (APP_ENV=test)."""

    def __init__(self, bucket: str) -> None:
        self.bucket = bucket
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, content_type: str) -> str:
        self.objects[key] = data
        return f"s3://{self.bucket}/{key}"

    def get(self, url: str) -> bytes:
        return self.objects[_split(url)[1]]

    def remove(self, url: str) -> None:
        self.objects.pop(_split(url)[1], None)


class MinioStorage:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str) -> None:
        p = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
        self.client = Minio(p.netloc, access_key=access_key, secret_key=secret_key, secure=p.scheme == "https")
        self.bucket = bucket
        self._bucket_ready = False
        self._lock = threading.Lock()

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        with self._lock:
            if self._bucket_ready:
                return
            if not self.client.bucket_exists(self.bucket):
                try:
                    self.client.make_bucket(self.bucket)
                except S3Error as exc:  # tiến trình khác vừa tạo xong
                    if exc.code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                        raise
            self._bucket_ready = True

    def put(self, key: str, data: bytes, content_type: str) -> str:
        try:
            self._ensure_bucket()
            self.client.put_object(self.bucket, key, io.BytesIO(data), len(data), content_type=content_type)
        except (S3Error, OSError, HTTPError) as exc:
            raise StorageUnavailable(str(exc)) from exc
        return f"s3://{self.bucket}/{key}"

    def get(self, url: str) -> bytes:
        bucket, key = _split(url)
        try:
            resp = self.client.get_object(bucket, key)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()
        except (S3Error, OSError, HTTPError) as exc:
            raise StorageUnavailable(str(exc)) from exc

    def remove(self, url: str) -> None:
        bucket, key = _split(url)
        try:
            self.client.remove_object(bucket, key)
        except (S3Error, OSError, HTTPError) as exc:
            raise StorageUnavailable(str(exc)) from exc


@lru_cache
def default_storage() -> ObjectStorage:
    s = get_settings()
    if s.app_env == "test":
        return InMemoryStorage(s.s3_bucket)
    return MinioStorage(s.s3_endpoint, s.s3_access_key, s.s3_secret_key, s.s3_bucket)
