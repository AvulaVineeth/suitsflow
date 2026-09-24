import asyncio
from unittest.mock import patch

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
