from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from suitsflow.api.routes.documents import get_storage
from suitsflow.core.config import Settings
from suitsflow.services.storage import S3Storage


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"s3_bucket": "personal-bucket"},
        {"s3_bucket": "personal-bucket", "s3_expected_bucket_owner": "123456789012"},
        {"s3_bucket": "personal-bucket", "s3_profile": "suitsflow-personal"},
    ],
)
def test_local_storage_requires_explicit_account(values) -> None:
    settings = Settings(_env_file=None, environment="local", **values)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
    with patch("boto3.session.Session") as session, pytest.raises(HTTPException) as error:
        get_storage(request)
    assert error.value.status_code == 503
    session.assert_not_called()


def test_local_profile_is_selected_without_resolving_credentials() -> None:
    settings = Settings(
        _env_file=None,
        environment="local",
        s3_bucket="personal-bucket",
        s3_profile="suitsflow-personal",
        s3_expected_bucket_owner="123456789012",
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
    with patch("boto3.session.Session") as session:
        storage = get_storage(request)
    assert isinstance(storage, S3Storage)
    assert storage.profile == "suitsflow-personal"
    assert storage.expected_owner == "123456789012"
    session.assert_not_called()
