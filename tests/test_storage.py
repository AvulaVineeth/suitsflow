import base64
import hashlib
from io import BytesIO
from unittest.mock import patch

import boto3
import pytest
from botocore.stub import Stubber

from suitsflow.services.storage import S3Storage, StorageUnavailable


@pytest.mark.parametrize("version_id", [None, "object-version-123"])
def test_s3_checksum_conditional_write_and_version(version_id: str | None) -> None:
    client = boto3.client(
        "s3", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test"
    )
    body = BytesIO(b"agreement")
    checksum = hashlib.sha256(body.getvalue())
    params = {
        "Bucket": "private-test",
        "ExpectedBucketOwner": "123456789012",
        "Key": "tenant/document/attempt",
        "Body": body,
        "ContentLength": 9,
        "ContentType": "text/plain",
        "ChecksumSHA256": base64.b64encode(checksum.digest()).decode(),
        "IfNoneMatch": "*",
    }
    with Stubber(client) as stubber, patch("boto3.session.Session.client", return_value=client):
        stubber.add_response("put_object", {"VersionId": version_id} if version_id else {}, params)
        stored = S3Storage("private-test", "us-east-1", "123456789012").put(
            params["Key"], body, size=9, checksum=checksum.hexdigest(), mime_type="text/plain"
        )
        assert stored.version_id == version_id
        assert stored.bucket == "private-test"
        assert stored.key == params["Key"]
        stubber.assert_no_pending_responses()


def test_s3_errors_are_not_exposed() -> None:
    client = boto3.client(
        "s3", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test"
    )
    with Stubber(client) as stubber, patch("boto3.session.Session.client", return_value=client):
        stubber.add_client_error("put_object", service_error_code="AccessDenied")
        with pytest.raises(StorageUnavailable):
            S3Storage("private-test", "us-east-1", "123456789012").put(
                "key", BytesIO(b"x"), size=1, checksum="a" * 64, mime_type="text/plain"
            )
