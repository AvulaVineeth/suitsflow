import pytest
from botocore.endpoint import Endpoint


@pytest.fixture(autouse=True)
def isolate_aws(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Tests must never resolve workstation credentials or send AWS requests."""
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    for name in (
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_ROLE_ARN",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    ):
        monkeypatch.delenv(name, raising=False)

    def deny_request(*args, **kwargs):
        raise AssertionError("Live AWS requests are forbidden in tests")

    monkeypatch.setattr(Endpoint, "make_request", deny_request)
