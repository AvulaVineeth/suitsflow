"""Private object storage; credentials come from the standard AWS credential chain."""

import base64
import hashlib
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, BinaryIO, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


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

    def download(
        self, reference: StoredObject, target: BinaryIO, *, size: int, checksum: str
    ) -> None: ...


class S3Storage:
    def __init__(
        self, bucket: str, region: str, expected_owner: str, profile: str | None = None
    ) -> None:
        self.bucket = bucket
        self.region = region
        self.expected_owner = expected_owner
        self.profile = profile

    @contextmanager
    def _client(self) -> Iterator["S3Client"]:
        with closing(
            boto3.session.Session(profile_name=self.profile).client(
                "s3",
                region_name=self.region,
                config=Config(
                    connect_timeout=5,
                    read_timeout=30,
                    retries={"mode": "standard", "total_max_attempts": 2},
                ),
            )
        ) as client:
            yield client

    def put(
        self, key: str, body: BinaryIO, *, size: int, checksum: str, mime_type: str
    ) -> StoredObject:
        try:
            # Create clients inside the worker thread, never during application startup.
            with self._client() as client:
                result = client.put_object(
                    Bucket=self.bucket,
                    ExpectedBucketOwner=self.expected_owner,
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

    def download(
        self, reference: StoredObject, target: BinaryIO, *, size: int, checksum: str
    ) -> None:
        if reference.bucket != self.bucket:
            raise StorageUnavailable
        try:
            with self._client() as client:
                # Use the persisted object version, never a caller-provided key or version.
                if reference.version_id is None:
                    result = client.get_object(
                        Bucket=reference.bucket,
                        Key=reference.key,
                        ExpectedBucketOwner=self.expected_owner,
                    )
                else:
                    result = client.get_object(
                        Bucket=reference.bucket,
                        Key=reference.key,
                        VersionId=reference.version_id,
                        ExpectedBucketOwner=self.expected_owner,
                    )
                with closing(result["Body"]) as body:
                    if result.get("ContentLength") != size:
                        raise StorageUnavailable
                    digest, received = hashlib.sha256(), 0
                    deadline = time.monotonic() + 120
                    while chunk := body.read(65536):
                        received += len(chunk)
                        if received > size or time.monotonic() > deadline:
                            raise StorageUnavailable
                        digest.update(chunk)
                        target.write(chunk)
                    if received != size or digest.hexdigest() != checksum:
                        raise StorageUnavailable
            target.seek(0)
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailable from exc
