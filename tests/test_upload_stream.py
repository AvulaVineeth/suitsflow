import asyncio
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from suitsflow.core.security import Principal
from suitsflow.services.upload_validation import InvalidUpload
from suitsflow.services.uploads import UploadService


@pytest.mark.parametrize("failure", ["timeout", "oversize", "disconnect", "format"])
def test_bad_stream_never_reaches_storage(failure: str) -> None:
    content = b"abc"
    repo = SimpleNamespace(
        session=SimpleNamespace(rollback=AsyncMock()),
        version=AsyncMock(
            return_value=SimpleNamespace(
                file_size=3,
                checksum=hashlib.sha256(content).hexdigest(),
                mime_type="application/pdf" if failure == "format" else "text/plain",
            )
        ),
    )
    storage = Mock()

    async def chunks():
        if failure == "timeout":
            await asyncio.sleep(1)
        if failure == "disconnect":
            raise ConnectionError("Client disconnected")
        yield content
        if failure == "oversize":
            yield b"extra"

    expected = {"timeout": TimeoutError, "disconnect": ConnectionError}.get(failure, InvalidUpload)
    with pytest.raises(expected):
        asyncio.run(
            UploadService(repo, storage).upload(
                Principal(uuid4(), uuid4(), frozenset({"tenant_admin"})),
                uuid4(),
                uuid4(),
                chunks(),
                "application/pdf" if failure == "format" else "text/plain",
                0.05,
            )
        )
    storage.put.assert_not_called()
    assert repo.version.await_count == 1
