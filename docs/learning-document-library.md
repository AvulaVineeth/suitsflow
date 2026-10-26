# Learning: connecting the document pipeline to a UI

The library turns existing backend state into something a person can inspect.
It does not run extraction or call an LLM. That separation makes the screen useful
now and keeps future AI processing behind the same authorization boundary.

## Follow one click

1. The library reads `GET /api/v1/documents?limit=20&offset=0`.
2. Selecting a document reads its `/versions` endpoint.
3. Selecting a revision reads `/scan-job` and `/extraction-job` independently.
4. On a cleared revision, **Read saved text** reads `/extraction`.

The last request reads a saved artifact. It does not call the on-demand `/text`
parser. Opening the screen should not unexpectedly repeat expensive processing.
Opening the screen cannot enqueue work. Explicit administrator actions now register
documents and enqueue processing; browsing still performs reads only.

## Separate state from interpretation

`content_status` answers whether a file is cleared, rejected or awaiting scanning.
Job status answers whether a particular queued attempt is pending, running,
completed or failed. These are different facts. A manual scan can clear a file
without creating a queued job, so “No queued job” does not mean “never scanned.”

An HTTP 404 for a job means there is no readable job at that scoped endpoint.
A 503 means the request failed. Displaying both as “no job” would hide an outage.
The UI treats each request's loading, success, empty and error states explicitly.

## Prevent stale results from changing the screen

Imagine selecting document A, then B before A's response arrives. The query
components are keyed by document, revision, page and refresh generation. Unmounting
a query aborts its request. It also checks the abort signal before changing state,
because a response might already be resolving when cancellation happens.
Disconnecting remounts the entire workspace, clearing data from the old session.
The `useRead` hook is deliberately mount-scoped: every caller must preserve these
identity keys when adding a new query.

This is useful in AI interfaces too: a slow response from an earlier question
must not overwrite the answer associated with the user's current question.

## Render document text as data

React renders extracted text inside a `pre` element as a string. There is no raw
HTML insertion, so a document containing `<script>` is displayed as text. Later
LLM integration needs its own prompt-injection boundaries; safe HTML rendering
alone does not make document instructions trustworthy.

## Keep demo and authenticated data distinct

Both adapters implement a small `Library` interface. The sample adapter uses
bundled examples and cannot contact storage. The API adapter makes authenticated
reads to the local backend. There is no automatic fallback to sample data after
an API error. The screen must not disguise a broken connection as real results.

Development tokens stay in memory rather than localStorage or URLs. That limits
persistence, but it is not a production identity system. Backend authorization is
still authoritative; hiding a button is never an access-control mechanism.

## Verification

Playwright exercises the actual screen with intercepted HTTP responses, including
unauthorized requests, server failures, late responses, text containing HTML, and
pagination. It checks the mobile viewport for horizontal overflow. The existing
backend integration suite separately checks the real database and authorization.
These tests complement one another; browser mocks alone do not prove that a live
deployment, identity provider or S3 account is configured correctly.

## Mutations and uncertain outcomes

The registration form sends one POST and opens the returned document. An in-flight
guard prevents duplicate submissions. A network failure is reported as an unknown
outcome because the database may already have committed. Automatically repeating
a non-idempotent create could produce another document. The form therefore asks
the user to refresh and check before submitting again.

Queue endpoints are idempotent for an existing active job. Even so, the UI waits
for the server response before displaying queued status and never claims that
queueing means processing has completed. Eligibility controls improve usability;
backend tenant, role and revision checks remain authoritative.
