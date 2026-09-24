"""Private object storage; credentials come from the standard AWS credential chain."""

import base64
from contextlib import closing
from dataclasses import dataclass
from typing import BinaryIO, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class StorageUnavailable(Exception):
    pass


@dataclass(frozen=True)
class StoredObject:
    bucket: str
    key: str
    version_id: str | None


class ObjectStorage(Protocol):
    def put(
        self, key: str, body: BinaryIO, *, size: int, checksum: str, mime_type: str
    ) -> StoredObject: ...


class S3Storage:
    def __init__(self, bucket: str, region: str) -> None:
        self.bucket = bucket
        self.region = region

    def put(
        self, key: str, body: BinaryIO, *, size: int, checksum: str, mime_type: str
    ) -> StoredObject:
        try:
            # Create clients inside the worker thread, never during application startup.
            with closing(
                boto3.session.Session().client(
                    "s3",
                    region_name=self.region,
                    config=Config(
                        connect_timeout=5,
                        read_timeout=30,
                        retries={"mode": "standard", "total_max_attempts": 2},
                    ),
                )
            ) as client:
                result = client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=body,
                    ContentLength=size,
                    ContentType=mime_type,
                    ChecksumSHA256=base64.b64encode(bytes.fromhex(checksum)).decode("ascii"),
                    IfNoneMatch="*",
                )
            return StoredObject(self.bucket, key, result.get("VersionId"))
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailable from exc
