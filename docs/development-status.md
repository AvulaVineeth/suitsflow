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

Document registration and processing controls `633939b` passed exact-commit CI
and are merged, alongside the earlier library and extraction foundation.
Current branch `feat/contract-review-graph` adds an internal LangGraph review path,
strict evidence validation, bounded retries, current-membership checks and an
injected model protocol. External tracing is explicitly disabled. No real model,
API endpoint, review persistence, approval flow or durable checkpointing exists yet.
Local validation: 151 tests passed, one Linux-only skip; lint, formatting and
strict typing passed. Exact-commit CI must pass before merge. All model calls in tests are fake; AWS remains untouched.

Local Docker image refresh remains blocked by UnknownIssuer when downloading
packages. Trying the container system trust store did not resolve it; no TLS
verification was disabled and the Dockerfile remains unchanged. The local API image
may lag these changes. The development database was last observed empty.
No live AWS calls were made; extraction jobs are tested with in-memory storage.

## Next slices

1. Validate and merge the bounded contract-review graph.
2. Add durable review records, audits and background review jobs before API/UI exposure.
3. Add a model adapter and semantic/prompt-injection evaluations; real Bedrock requires personal AWS confirmation.
4. Continue revision upload UI, indexing, production identity and worker supervision.
5. Reconcile private objects orphaned by interrupted uploads.

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
