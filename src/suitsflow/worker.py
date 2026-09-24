"""Bounded queue drain; process supervision and scheduling belong to deployment."""

import argparse
import asyncio

from suitsflow.core.config import Settings, get_settings
from suitsflow.db.session import Database
from suitsflow.services.scan_jobs import ScanJobs
from suitsflow.services.scanner import ClamAVScanner
from suitsflow.services.storage import S3Storage


async def drain(settings: Settings, max_jobs: int) -> int:
    if not 1 <= max_jobs <= 1000:
        raise ValueError("max_jobs must be between 1 and 1000")
    if (
        settings.s3_bucket is None
        or settings.s3_expected_bucket_owner is None
        or (settings.environment in {"local", "test"} and settings.s3_profile is None)
        or settings.clamav_host is None
    ):
        raise ValueError("Explicit storage account and scanner configuration are required")
    storage = S3Storage(
        settings.s3_bucket,
        settings.s3_region,
        settings.s3_expected_bucket_owner,
        settings.s3_profile,
    )
    scanner = ClamAVScanner(
        settings.clamav_host,
        settings.clamav_port,
        settings.clamav_timeout_seconds,
        max_file_bytes=settings.clamav_max_file_bytes,
        max_scan_bytes=settings.clamav_max_scan_bytes,
    )
    database = Database(settings)
    processed = 0
    try:
        for _ in range(max_jobs):
            async with database.sessions() as session:
                if not await ScanJobs(session).run_one(storage, scanner):
                    break
                processed += 1
        return processed
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued document scans")
    parser.add_argument("--max-jobs", type=int, default=1)
    args = parser.parse_args()
    try:
        count = asyncio.run(drain(get_settings(), args.max_jobs))
    except ValueError as exc:
        parser.error(str(exc))
    else:
        print(f"Processed {count} scan jobs")


if __name__ == "__main__":
    main()
