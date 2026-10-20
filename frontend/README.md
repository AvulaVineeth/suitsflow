# SuitsFlow document library

React and TypeScript client for the existing tenant-scoped document API.
This first slice is read-only: browse documents and revisions, inspect scan and
extraction jobs, and read saved text. Uploads, job submission and production sign-in
are not part of this screen yet.

## Run locally

Use Node 24 and npm. From this directory:

```sh
npm ci
npm run dev
```

Open http://127.0.0.1:5173. The default **Sample preview** uses bundled fixtures;
it sends no API requests, uploads no files, and requires no AWS account.
Select a document, then **Read saved text** on a cleared revision.

**Connect local API** sends reads through the development proxy to
http://127.0.0.1:8000. The backend must be running with current migrations and
an explicitly configured development identity and token. Enter that application's
development bearer token, never an AWS key. No credentials are bundled here.
The token lives in memory; disconnecting or reloading drops it. Requests use
Authorization headers, never query strings, and bypass browser caching.
The server remains responsible for tenant and role authorization.

The existing container API may lag the repository if its image build fails due
to the local certificate trust issue. Sample preview remains available independently.
An empty development database will show an empty library. The UI does not seed it.
Real saved-text reads require the backend's storage configuration; live AWS remains
deferred until a personal account is explicitly confirmed.

Search filters the current 20-document page. Use Previous/Next for more documents
or revisions. **Refresh library** reloads documents and clears the selected revision;
**Refresh jobs** reloads the selected revision's jobs and any visible saved text.
There is no automatic polling. A missing job is distinct from a failed request.
A completed manual scan can exist without a queued scan job.

## Check changes

```sh
npm run check
npm run build
npx playwright install chromium
npm test
```

Browser tests intercept API requests and cover authorization failures, safe text
rendering, session cleanup, stale responses, pagination and mobile layout.
CI runs these checks alongside the backend suite. `npm run format` formats sources.
The lockfile pins transitive dependencies. On machines with a trusted corporate
certificate installed, Node 24 can use `NODE_USE_SYSTEM_CA=1`; never disable TLS
verification to install packages.

## Deployment boundary

`npm run build` writes static assets to `dist`. The Vite development proxy is not
part of those assets. A future deployment must serve the UI and `/api` through
an approved same-origin gateway and replace development authentication with the
planned production identity flow. Do not expose the development server publicly.

See [the learning guide](../docs/learning-document-library.md) for the design rationale.
