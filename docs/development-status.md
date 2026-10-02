# Development handoff

Updated October 1, 2026.

## Implemented and merged

- Tenant, membership, document and immutable revision foundations with atomic audits.
- Verified upload/download adapters; live AWS remains unconfigured and untested.
- Quarantine lifecycle and local ClamAV protocol/engine checks.
- Durable scan jobs with leases, stale-worker fencing and explicit retries (`bfbee2b`).
- Bounded UTF-8 extraction with exact revision provenance (`8383f96`).
- Bounded DOCX main-body extraction (`5f3ade6`); headers, notes and formatting excluded.

## Current slice

PDF extraction `7aa6a26` passed CI and is merged. The current branch
`feat/saved-extraction-artifacts` adds migration 0008 and POST/GET `/extraction`.
Extracted UTF-8 text remains in private object storage; immutable PostgreSQL metadata
links it to tenant, revision, source checksum, parser version and output checksum.
Metadata and audit commit together. Repeated saves reuse a record; concurrent
first saves converge to one published record. Unreferenced private objects from
failed writes or concurrent losers need later reconciliation.

Local lint, formatting and type checks pass. The full local suite passed 127 tests
with one Linux-only skip; exact-commit CI must pass before merge. No live AWS calls are used; tests inject in-memory storage.
The learning walkthrough is `docs/learning-extraction-pipeline.md`.

## Next slices

1. Add durable extraction jobs with queued/running/completed/failed states.
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
