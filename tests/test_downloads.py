import asyncio
import hashlib
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber
from starlette.requests import ClientDisconnect

from suitsflow.api.download_response import DownloadResponse
from suitsflow.core.security import Principal
from suitsflow.services.downloads import Download, DownloadService
from suitsflow.services.storage import S3Storage, StorageUnavailable, StoredObject


@pytest.mark.parametrize("version_id", [None, "exact-stored-version"])
@pytest.mark.parametrize("failure", [None, "hash", "length", "truncated", "missing", "oversize"])
def test_verified_download(version_id: str | None, failure: str | None) -> None:
    client = boto3.client(
        "s3", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test"
    )
    content = b"contract"
    checksum = hashlib.sha256(content).hexdigest()
    data = {"hash": b"tampered", "truncated": b"short", "oversize": b"too much content"}.get(
        failure, content
    )
    raw = BytesIO(data)
    params = {"Bucket": "private-test", "Key": "stored-key", "ExpectedBucketOwner": "123456789012"}
    if version_id is not None:
        params["VersionId"] = version_id
    storage = S3Storage("private-test", "us-east-1", "123456789012")
    with Stubber(client) as stubber, patch("boto3.session.Session.client", return_value=client):
        if failure == "missing":
            stubber.add_client_error(
                "get_object", service_error_code="NoSuchKey", expected_params=params
            )
        else:
            stubber.add_response(
                "get_object",
                {
                    "Body": StreamingBody(raw, len(data)),
                    "ContentLength": len(content) + (1 if failure == "length" else 0),
                },
                params,
            )
        target = BytesIO()
        reference = StoredObject("private-test", "stored-key", version_id)
        if failure:
            with pytest.raises(StorageUnavailable):
                storage.download(reference, target, size=len(content), checksum=checksum)
        else:
            storage.download(reference, target, size=len(content), checksum=checksum)
            assert target.read() == content
        if failure != "missing":
            assert raw.closed
        stubber.assert_no_pending_responses()


def test_bucket_mismatch_never_creates_aws_client() -> None:
    with patch("boto3.session.Session") as session, pytest.raises(StorageUnavailable):
        S3Storage("personal-bucket", "us-east-1", "123456789012").download(
            StoredObject("wrong-bucket", "key", None), BytesIO(), size=1, checksum="a" * 64
        )
    session.assert_not_called()


@pytest.mark.parametrize("disconnect", [False, True])
def test_response_closes_temporary_file(disconnect: bool) -> None:
    body = BytesIO(b"contract")
    response = DownloadResponse(Download(body, 8, "revision.txt"))
    sent = []

    async def send(message):
        if disconnect:
            raise OSError("client disconnected")
        sent.append(message)

    async def receive():
        return {"type": "http.disconnect"}

    async def run():
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)

    if disconnect:
        with pytest.raises(ClientDisconnect):
            asyncio.run(run())
    else:
        asyncio.run(run())
        assert b"".join(item.get("body", b"") for item in sent) == b"contract"
    assert body.closed


def test_failed_storage_read_closes_temporary_file() -> None:
    files = []

    def fail(reference, target, **kwargs):
        files.append(target)
        target.write(b"partial")
        raise StorageUnavailable

    version = SimpleNamespace(
        uploaded_at=True,
        content_status="clean",
        storage_bucket="private-test",
        storage_key="key",
        storage_version_id="version",
        file_size=8,
        checksum="a" * 64,
        mime_type="text/plain",
        version_number=1,
    )
    repository = SimpleNamespace(
        version=AsyncMock(return_value=version), session=SimpleNamespace(rollback=AsyncMock())
    )
    service = DownloadService(repository, SimpleNamespace(download=fail))
    with pytest.raises(StorageUnavailable):
        asyncio.run(
            service.download(Principal(uuid4(), uuid4(), frozenset({"member"})), uuid4(), uuid4())
        )
    assert len(files) == 1 and files[0].closed
