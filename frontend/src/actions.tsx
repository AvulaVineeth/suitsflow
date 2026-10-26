import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  type Document,
  type Job,
  type LibraryActions,
  type Revision,
} from "./api";

// Requests are never automatically retried. Aborting a request does not undo a server commit.
function useMutation() {
  const active = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(
    () => () => {
      active.current?.abort();
    },
    [],
  );
  async function run<T>(
    request: (signal: AbortSignal) => Promise<T>,
    success: (result: T) => void,
  ) {
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setError("");
    try {
      const result = await request(controller.signal);
      if (!controller.signal.aborted) success(result);
    } catch (cause) {
      if (!controller.signal.aborted)
        setError(
          cause instanceof ApiError
            ? cause.message
            : "The result could not be confirmed. Refresh before trying again; the request may have succeeded.",
        );
    } finally {
      if (!controller.signal.aborted) {
        active.current = null;
        setBusy(false);
      }
    }
  }
  return { run, busy, error };
}

export function RegisterDocument({
  actions,
  onCreated,
  onClose,
}: {
  actions: LibraryActions;
  onCreated: (document: Document) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState<"contract" | "policy" | "other">("contract");
  const mutation = useMutation();
  return (
    <form
      className="connect-form register-form"
      aria-label="Register document"
      onSubmit={(event) => {
        event.preventDefault();
        if (!name.trim() || mutation.error) return;
        void mutation.run(
          (signal) => actions.createDocument(name.trim(), type, signal),
          onCreated,
        );
      }}
    >
      <h3>Register a document</h3>
      <p className="muted">
        Creates a document record. File upload is a separate step. Tenant
        administrator access is required.
      </p>
      <label>
        Document name
        <input
          required
          maxLength={255}
          value={name}
          disabled={mutation.busy}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label>
        Document type
        <select
          value={type}
          disabled={mutation.busy}
          onChange={(event) => setType(event.target.value as typeof type)}
        >
          <option value="contract">Contract</option>
          <option value="policy">Policy</option>
          <option value="other">Other</option>
        </select>
      </label>
      {mutation.error && (
        <p className="error" role="alert">
          {mutation.error} Close this form and check the library before
          submitting a new request.
        </p>
      )}
      <button
        className="primary"
        disabled={mutation.busy || !!mutation.error || !name.trim()}
      >
        {mutation.busy ? "Registering…" : "Register document"}
      </button>
      <button type="button" disabled={mutation.busy} onClick={onClose}>
        Close
      </button>
    </form>
  );
}

export function QueueAction({
  actions,
  revision,
  kind,
  job,
  onQueued,
}: {
  actions: LibraryActions;
  revision: Revision;
  kind: "scan" | "extraction";
  job: Job | null;
  onQueued: (job: Job) => void;
}) {
  const mutation = useMutation();
  const allowed =
    kind === "extraction"
      ? revision.content_status === "clean"
      : revision.content_status === "pending_scan" ||
        revision.content_status === "scan_failed";
  if (!allowed || (job && job.status !== "failed")) return null;
  return (
    <div className="queue-action">
      <button
        disabled={mutation.busy || !!mutation.error}
        onClick={() => {
          void mutation.run(
            (signal) =>
              actions.enqueue(revision.document_id, revision.id, kind, signal),
            onQueued,
          );
        }}
      >
        {mutation.busy ? "Submitting…" : `${job ? "Retry" : "Queue"} ${kind}`}
      </button>
      {mutation.error && (
        <p role="alert" className="error">
          {mutation.error}
        </p>
      )}
    </div>
  );
}
