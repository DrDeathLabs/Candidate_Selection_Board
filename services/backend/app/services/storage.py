from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StorageObjectRef:
    bucket: str
    key: str


class ObjectStorageService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client: BaseClient = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.minio_root_user,
            aws_secret_access_key=settings.minio_root_password,
        )
        self.bucket = settings.minio_bucket
        self._bucket_ready = False

    def build_object_ref(self, case_id: str, file_name: str) -> StorageObjectRef:
        return StorageObjectRef(bucket=self.bucket, key=f"{case_id}/{file_name}")

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)
        self._bucket_ready = True

    def upload_bytes(self, object_ref: StorageObjectRef, data: bytes, *, content_type: str) -> None:
        self._ensure_bucket()
        self.client.upload_fileobj(
            BytesIO(data),
            object_ref.bucket,
            object_ref.key,
            ExtraArgs={"ContentType": content_type},
        )

    def get_bytes(self, object_ref: StorageObjectRef) -> bytes:
        response = self.client.get_object(Bucket=object_ref.bucket, Key=object_ref.key)
        return response["Body"].read()

    def delete_object(self, object_ref: StorageObjectRef) -> None:
        try:
            self.client.delete_object(Bucket=object_ref.bucket, Key=object_ref.key)
        except ClientError as exc:
            logger.error("S3 delete failed for %s/%s: %s", object_ref.bucket, object_ref.key, exc)
