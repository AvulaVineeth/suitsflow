# Development handoff

Updated October 26, 2026.

## Implemented and merged

- Tenant, membership, document and immutable revision foundations with atomic audits.
- Verified upload/download adapters; live AWS remains unconfigured and untested.
- Quarantine lifecycle and local ClamAV protocol/engine checks.
- Durable scan jobs with leases, stale-worker fencing and explicit retries (`bfbee2b`).
- Bounded UTF-8 extraction with exact revision provenance (`8383f96`).
- Bounded DOCX main-body extraction (`5f3ade6`); headers, notes and formatting excluded.

## Current slice

Saved artifacts `7669f7e`, extraction jobs `3699e2f`, and the document-library UI
`0954d6c` passed exact-commit CI and are merged. The current branch
`feat/document-library-actions` adds document registration and eligible scan/
extraction enqueue/retry controls. Sample mode remains read-only. API authorization
is authoritative, writes are not automatically retried, and uncertain responses
require refreshing before another attempt. No backend or migration changes.
The frontend build and 12 browser tests pass locally. Exact-commit CI gates
the merge. Tests use intercepted HTTP requests; no live AWS calls were made.

Local Docker image refresh remains blocked by UnknownIssuer when downloading
packages. Trying the container system trust store did not resolve it; no TLS
verification was disabled and the Dockerfile remains unchanged. The local API image
may lag these changes. The development database was last observed empty.
No live AWS calls were made; extraction jobs are tested with in-memory storage.

## Next slices

1. Validate and merge document registration and queue controls.
2. Add revision registration/upload UI; live storage requires personal AWS confirmation.
3. Add indexing, production identity, automatic scan enqueue and worker supervision.
4. Reconcile private objects orphaned by interrupted uploads.

## Seeing progress and deployment boundaries

The local API explorer is http://127.0.0.1:8000/docs. Rebuild/restart the API after
changes with `docker compose up -d --build api`. The document-library UI runs at
http://127.0.0.1:5173 with `npm run dev` from `frontend/`; see its README for setup.
Sample preview is independent of the backend and is not evidence of live storage.
GitHub Actions records validation for each commit.
Development authentication remains local/test only. Real scanner signature
freshness and production deployment are unverified. Do not inspect, restore or use
company AWS credentials. Personal AWS integration requires explicit confirmation.
The September 24 overnight session ended; later work is user-requested interactive
development, not a resumed schedule.
