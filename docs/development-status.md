# Development handoff

Updated September 26, 2026.

## Implemented and merged

- Tenant, membership, document and immutable revision foundations with atomic audits.
- Verified upload/download adapters; live AWS remains unconfigured and untested.
- Quarantine lifecycle and local ClamAV protocol/engine tests.
- Durable scan jobs, 15-minute leases, stale-worker fencing, explicit retries and
  fresh membership checks. Commit `bfbee2b` passed remote CI and is merged into main.

## Current slice

`feat/plain-text-extraction` adds on-demand UTF-8 extraction from clean revisions,
with bounded input/output and exact revision/checksum/extractor provenance.
All 106 local tests, lint, formatting and type checks pass. Exact-commit remote CI
must pass before merge.
A Windows checkout issue in Linux scanner fixture line endings was fixed using
`.gitattributes`; the local test scanner is healthy again.

## Next slices and boundaries

1. Validate and merge the extraction slice.
2. Add bounded PDF/DOCX extraction, then persisted extraction artifacts and indexing.
3. Reconcile private objects orphaned by interrupted uploads.
4. Add production identity, automatic scan enqueue and worker supervision.

Development authentication is still local/test only. Real scanner signature
freshness and production deployment remain unverified. Do not inspect, restore,
or use company AWS credentials. Personal AWS integration requires explicit owner
confirmation. Local mocks and test services remain the development path.

The September 24 overnight session has ended. Subsequent work is explicitly
requested interactive development; do not resume or recreate that schedule.
