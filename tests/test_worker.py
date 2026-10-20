import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from suitsflow.core.config import Settings
from suitsflow.worker import drain


@pytest.mark.parametrize("max_jobs", [0, 1001, 1])
def test_worker_requires_explicit_configuration_before_clients(max_jobs):
    with patch("suitsflow.worker.S3Storage") as storage, patch("suitsflow.worker.Database") as db:
        with pytest.raises(ValueError):
            asyncio.run(drain(Settings(_env_file=None), max_jobs))
        storage.assert_not_called()
        db.assert_not_called()


def test_extraction_queue_needs_storage_but_no_scanner():
    settings = Settings(
        _env_file=None,
        environment="test",
        s3_bucket="private-test",
        s3_profile="test-only",
        s3_expected_bucket_owner="123456789012",
        clamav_host=None,
    )
    with (
        patch("suitsflow.worker.S3Storage"),
        patch("suitsflow.worker.Database") as db,
        patch("suitsflow.worker.ClamAVScanner") as scanner,
        patch(
            "suitsflow.worker.ExtractionJobs.run_one", new=AsyncMock(side_effect=[True, False])
        ) as run,
    ):
        db.return_value.dispose = AsyncMock()
        assert asyncio.run(drain(settings, 10, "extractions")) == 1
        assert run.await_count == 2
        scanner.assert_not_called()
        db.return_value.dispose.assert_awaited_once()
