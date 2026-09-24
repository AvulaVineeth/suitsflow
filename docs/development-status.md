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
Scanning is synchronous and holds the revision row lock during external I/O.
Clean is a scanner verdict, not a promise of harmless content or processing readiness.

## Next coherent slices

1. Local real-engine scanning tests are implemented; verify exact-commit CI and merge status.
2. Add durable background processing and retry/claim handling for scanning and extraction.
3. Extract bounded text from cleared documents, preserving exact revision provenance.
4. Add reconciliation for private storage objects orphaned by interrupted writes.
5. Add production identity and further product workflows from the architecture contract.

Live AWS work is deferred until the owner explicitly confirms a personal account.
Do not inspect, restore, or use company credentials. Local/mock work can continue.
Only merge slices after local quality checks and exact-commit remote CI pass.
