# Development handoff

Updated September 24, 2026 during the overnight development session.

## Implemented

- PostgreSQL tenant, membership, document, and revision foundations.
- Tenant-scoped authorization and atomic audit records.
- Verified S3 upload and download adapters, exercised with mocked AWS responses.
- Explicit local AWS profile and expected bucket-owner settings; tests block live AWS.
- Scan lifecycle: pending upload, pending scan, clean, rejected, and scan failed.
- Administrator scan endpoint with a ClamAV INSTREAM adapter; downloads require clean status.
- Migration 0006 quarantines previously uploaded files instead of assuming they are clean.

## Validation and limitations

The scan slice was developed on `feat/document-scan-lifecycle`. Check Git history
and CI for the current merge and validation status.
Tests use disposable PostgreSQL, fake storage/scanner adapters, and socket mocks.
A real local ClamAV test daemon now verifies harmless custom signatures and
wire behavior; a production daemon with maintained signatures remains unverified.
No live AWS integration has been provisioned or tested. Real-engine tests exposed
an archive-limit edge case; application preflight now rejects over-limit ZIP entries.
Authentication remains the opt-in development token, not production identity.
Background scan jobs are implemented on `feat/background-document-scans`; 90 local tests and static checks pass; remote CI is pending.
The optional synchronous endpoint still holds a revision lock during I/O.
The background worker releases database transactions during external I/O and uses
15-minute leases with stale-claim fencing. Explicit enqueue and failed-job retry
are available; automatic upload enqueue and deployment supervision are not yet included.
Clean is a scanner verdict, not a promise of harmless content or processing readiness.

## Next coherent slices

1. Real-engine scanner checks passed CI and were merged at `0015538`.
2. Finish local/remote validation of background scan jobs before merging.
3. Extract bounded text from cleared documents, preserving exact revision provenance.
4. Add reconciliation for private storage objects orphaned by interrupted writes.
5. Add production identity and further product workflows from the architecture contract.

Live AWS work is deferred until the owner explicitly confirms a personal account.
Do not inspect, restore, or use company credentials. Local/mock work can continue.
Only merge slices after local quality checks and exact-commit remote CI pass.

## Resume checkpoint

Background scan jobs are implemented with migration 0007, queue/status endpoints,
a bounded worker CLI, lease recovery, current-membership checks, and atomic audits.
Local lint, format, and type checks pass. All 90 tests pass after fixing
a timestamp refresh on failed-job requeue. Check the latest commit and CI before
merging `feat/background-document-scans`; never merge a failing or unverified SHA.
The next independent product slice is bounded text extraction from clean revisions.
Weekly usage reached 100% during this checkpoint; no reset credit was redeemed.
