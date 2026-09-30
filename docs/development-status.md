# Development handoff

Updated September 30, 2026.

## Implemented and merged

- Tenant, membership, document and immutable revision foundations with atomic audits.
- Verified upload/download adapters; live AWS remains unconfigured and untested.
- Quarantine lifecycle and local ClamAV protocol/engine checks.
- Durable scan jobs with leases, stale-worker fencing and explicit retries (`bfbee2b`).
- Bounded UTF-8 extraction with exact revision provenance (`8383f96`).
- Bounded DOCX main-body extraction (`5f3ade6`); headers, notes and formatting excluded.

## Current slice

`feat/pdf-text-extraction` adds PDF text-layer extraction in Linux child processes.
Limits: 512 MiB address space, 10 seconds CPU, 15 seconds wall time, 2 MiB source,
100 pages, 8 MiB decoded page streams, 1,000,000 code points, two children per API
process. Encrypted, malformed and wholly textless PDFs fail; there is no OCR.
Native Windows returns unavailable; the Docker runtime supports the real worker.
Real worker checks passed in a network-disabled, read-only Linux container.
Local regression: 127 passed, one Linux-only test skipped on Windows; the real
worker passed separately in Docker. Lint, formatting and type checks pass.
Exact-commit CI must pass before merge.

## Next slices

1. Persist extraction artifacts and processing state with revision provenance.
2. Add a document-library UI for revisions, quarantine states and extracted text.
3. Add indexing, production identity, automatic scan enqueue and worker supervision.
4. Reconcile private objects orphaned by interrupted uploads.

## Seeing progress and deployment boundaries

The local API explorer is http://127.0.0.1:8000/docs. Rebuild/restart the API after
changes with `docker compose up -d --build api`. The product UI is not implemented.
GitHub Actions records validation for each commit.
Development authentication remains local/test only. Real scanner signature
freshness and production deployment are unverified. Do not inspect, restore or use
company AWS credentials. Personal AWS integration requires explicit confirmation.
The September 24 overnight session ended; later work is user-requested interactive
development, not a resumed schedule.
