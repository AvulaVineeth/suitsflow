import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ApiError,
  apiLibrary,
  PAGE_SIZE,
  type Document,
  type Library,
  type Revision,
} from "./api";
import { sampleLibrary } from "./sample";
import "./style.css";

function useRead<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<{
    data?: T;
    error?: string;
    loading: boolean;
  }>({ loading: true });
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ data, loading: false });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({
            error:
              error instanceof ApiError
                ? error.message
                : "Unable to load this content. Check your connection and refresh.",
            loading: false,
          });
      });
    return () => controller.abort();
  }, []); // Each query is mounted with a key containing its identity and refresh generation.
  return state;
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <p className="error" role="alert">
      {message}
    </p>
  );
}
function Loading() {
  return (
    <p className="muted" role="status">
      Loading…
    </p>
  );
}
const date = (value: string) =>
  new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
const statusNames: Record<string, string> = {
  pending_upload: "Awaiting upload",
  pending_scan: "Awaiting scan",
  clean: "Cleared",
  rejected: "Rejected",
  scan_failed: "Scan failed",
  pending: "Queued",
  running: "Processing",
  completed: "Completed",
  failed: "Failed",
};
function Badge({ status }: { status: string }) {
  return (
    <span className={`badge ${status}`}>{statusNames[status] ?? status}</span>
  );
}
function Pager({
  offset,
  count,
  onPage,
}: {
  offset: number;
  count: number;
  onPage: (offset: number) => void;
}) {
  return (
    <nav className="pager" aria-label="Pagination">
      <button
        disabled={offset === 0}
        onClick={() => onPage(Math.max(0, offset - PAGE_SIZE))}
      >
        Previous
      </button>
      <span>Page {offset / PAGE_SIZE + 1}</span>
      <button
        disabled={count < PAGE_SIZE}
        onClick={() => onPage(offset + PAGE_SIZE)}
      >
        Next
      </button>
    </nav>
  );
}
function DocumentPage({
  library,
  offset,
  selected,
  onSelect,
  onPage,
}: {
  library: Library;
  offset: number;
  selected?: string;
  onSelect: (document: Document) => void;
  onPage: (offset: number) => void;
}) {
  const state = useRead((signal) => library.documents(offset, signal));
  const [search, setSearch] = useState("");
  if (state.loading) return <Loading />;
  if (state.error) return <ErrorMessage message={state.error} />;
  const rows = state.data ?? [];
  const filtered = rows.filter((row) =>
    row.name.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <>
      <label className="search">
        Find on this page
        <input
          type="search"
          placeholder="Search documents…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>
      {rows.length === 0 ? (
        <div className="empty">
          <h3>No documents here yet</h3>
          <p>Documents registered through the API will appear here.</p>
        </div>
      ) : filtered.length === 0 ? (
        <p className="muted">No matching documents on this page.</p>
      ) : (
        <ul className="document-list">
          {filtered.map((row) => (
            <li key={row.id}>
              <button
                className={`document ${selected === row.id ? "selected" : ""}`}
                aria-pressed={selected === row.id}
                onClick={() => onSelect(row)}
              >
                <span className="file-icon" aria-hidden="true">
                  ≡
                </span>
                <span>
                  <strong>{row.name}</strong>
                  <small>
                    {row.document_type} · {date(row.created_at)}
                  </small>
                </span>
                <span aria-hidden="true">↗</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <Pager offset={offset} count={rows.length} onPage={onPage} />
    </>
  );
}
function SavedText({
  library,
  revision,
}: {
  library: Library;
  revision: Revision;
}) {
  const state = useRead((signal) =>
    library.text(revision.document_id, revision.id, signal),
  );
  if (state.loading) return <Loading />;
  if (state.error) return <ErrorMessage message={state.error} />;
  if (!state.data)
    return (
      <p className="muted">No saved text is available for this revision yet.</p>
    );
  return (
    <>
      <p className="muted">
        {state.data.extractor} · {state.data.character_count.toLocaleString()}{" "}
        characters
      </p>
      <pre className="extracted-text">{state.data.text}</pre>
    </>
  );
}
function JobStatus({
  library,
  revision,
  kind,
}: {
  library: Library;
  revision: Revision;
  kind: "scan" | "extraction";
}) {
  const state = useRead((signal) =>
    library.job(revision.document_id, revision.id, kind, signal),
  );
  return (
    <div className="job">
      <span>{kind === "scan" ? "Scan job" : "Extraction job"}</span>
      {state.loading ? (
        <Loading />
      ) : state.error ? (
        <ErrorMessage message={state.error} />
      ) : state.data ? (
        <span>
          <Badge status={state.data.status} />
          <small>
            {state.data.attempts} attempt{state.data.attempts === 1 ? "" : "s"}
          </small>
        </span>
      ) : (
        <span className="muted">No queued job</span>
      )}
    </div>
  );
}
function RevisionDetails({
  library,
  revision,
}: {
  library: Library;
  revision: Revision;
}) {
  const [showText, setShowText] = useState(false);
  const [refresh, setRefresh] = useState(0);
  return (
    <section className="details" aria-label="Revision details">
      <div className="section-heading">
        <h3>Revision {revision.version_number}</h3>
        <Badge status={revision.content_status} />
      </div>
      <dl>
        <dt>File type</dt>
        <dd>
          {revision.mime_type === "text/plain"
            ? "Plain text"
            : revision.mime_type === "application/pdf"
              ? "PDF"
              : "Word document"}
        </dd>
        <dt>Size</dt>
        <dd>{revision.file_size.toLocaleString()} bytes</dd>
        <dt>Registered</dt>
        <dd>{date(revision.created_at)}</dd>
        <dt>Source SHA-256</dt>
        <dd className="checksum">{revision.checksum}</dd>
      </dl>
      <div className="section-heading">
        <h3>Processing</h3>
        <button onClick={() => setRefresh((value) => value + 1)}>
          Refresh jobs
        </button>
      </div>
      <JobStatus
        key={`scan-${refresh}`}
        library={library}
        revision={revision}
        kind="scan"
      />
      <JobStatus
        key={`extraction-${refresh}`}
        library={library}
        revision={revision}
        kind="extraction"
      />
      <div className="text-section">
        <h3>Extracted text</h3>
        {revision.content_status !== "clean" ? (
          <p className="muted">
            Text is available only after this revision passes scanning.
          </p>
        ) : (
          <>
            <button
              className="primary"
              onClick={() => setShowText((value) => !value)}
            >
              {showText ? "Hide saved text" : "Read saved text"}
            </button>
            {showText && (
              <SavedText key={refresh} library={library} revision={revision} />
            )}
          </>
        )}
      </div>
    </section>
  );
}
function RevisionPage({
  library,
  document,
  offset,
  onPage,
}: {
  library: Library;
  document: Document;
  offset: number;
  onPage: (offset: number) => void;
}) {
  const state = useRead((signal) =>
    library.revisions(document.id, offset, signal),
  );
  const [selected, setSelected] = useState<Revision>();
  if (state.loading) return <Loading />;
  if (state.error) return <ErrorMessage message={state.error} />;
  const rows = state.data ?? [];
  const current = selected ?? rows[0];
  return (
    <>
      {rows.length === 0 ? (
        <p className="muted">No revisions on this page.</p>
      ) : (
        <div className="revision-tabs" aria-label="Revisions">
          {rows.map((row) => (
            <button
              key={row.id}
              className={current?.id === row.id ? "active" : ""}
              aria-pressed={current?.id === row.id}
              onClick={() => setSelected(row)}
            >
              Revision {row.version_number}
            </button>
          ))}
        </div>
      )}
      <Pager offset={offset} count={rows.length} onPage={onPage} />
      {current && (
        <RevisionDetails
          key={current.id}
          library={library}
          revision={current}
        />
      )}
    </>
  );
}
function Revisions({
  library,
  document,
}: {
  library: Library;
  document: Document;
}) {
  const [offset, setOffset] = useState(0);
  return (
    <>
      <div className="eyebrow">REVISION HISTORY</div>
      <h2>{document.name}</h2>
      <RevisionPage
        key={offset}
        library={library}
        document={document}
        offset={offset}
        onPage={setOffset}
      />
    </>
  );
}
function Workspace({ library }: { library: Library }) {
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Document>();
  return (
    <div className="workspace">
      <section className="panel library" aria-label="Documents">
        <div className="section-heading">
          <h2>All documents</h2>
          <span className="muted">Read-only</span>
        </div>
        <DocumentPage
          key={offset}
          library={library}
          offset={offset}
          selected={selected?.id}
          onSelect={setSelected}
          onPage={(value) => {
            setOffset(value);
            setSelected(undefined);
          }}
        />
      </section>
      <section className="panel inspector" aria-label="Document inspector">
        {selected ? (
          <Revisions key={selected.id} library={library} document={selected} />
        ) : (
          <div className="empty inspector-empty">
            <span className="large-icon" aria-hidden="true">
              ≡
            </span>
            <h2>A clear view of every revision</h2>
            <p>
              Select a document to inspect its history,
              <br />
              processing status, and extracted text.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
function App() {
  const [connection, setConnection] = useState<{
    library: Library;
    live: boolean;
  }>({ library: sampleLibrary, live: false });
  const [connecting, setConnecting] = useState(false);
  const [token, setToken] = useState("");
  const [generation, setGeneration] = useState(0);
  function disconnect() {
    setConnection({ library: sampleLibrary, live: false });
    setGeneration((value) => value + 1);
  }
  return (
    <>
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="SuitsFlow home">
          <span>S</span>SuitsFlow
        </a>
        <div className="sidebar-label">WORKSPACE</div>
        <div className="nav-active">
          ▤ <span>Documents</span>
        </div>
        <p className="sidebar-footer">
          Document intelligence,
          <br />
          built on a trusted foundation.
        </p>
      </aside>
      <main>
        <header>
          <span className="breadcrumb">
            Workspace / <strong>Documents</strong>
          </span>
          <span className={`connection ${connection.live ? "live" : ""}`}>
            {connection.live ? "Local API" : "Sample preview"}
          </span>
        </header>
        <div className="page">
          <div className="page-title">
            <div>
              <div className="eyebrow">YOUR DOCUMENT WORKSPACE</div>
              <h1>Document library</h1>
              <p className="muted">
                Every revision. A traceable path from file to text.
              </p>
            </div>
            <div className="actions">
              <button onClick={() => setGeneration((value) => value + 1)}>
                Refresh library
              </button>
              <button
                className="primary"
                onClick={() =>
                  connection.live
                    ? disconnect()
                    : setConnecting((value) => !value)
                }
              >
                {connection.live ? "Disconnect" : "Connect local API"}
              </button>
            </div>
          </div>
          {!connection.live && (
            <div className="notice">
              <strong>Explore with sample data.</strong> These example documents
              are not uploaded files. Connect the local API to view your
              workspace.
            </div>
          )}
          {connecting && !connection.live && (
            <form
              className="connect-form"
              onSubmit={(event) => {
                event.preventDefault();
                if (!token.trim()) return;
                setConnection({
                  library: apiLibrary(token.trim()),
                  live: true,
                });
                setToken("");
                setConnecting(false);
                setGeneration((value) => value + 1);
              }}
            >
              <label>
                Local development access token
                <input
                  type="password"
                  autoComplete="off"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  required
                />
              </label>
              <p className="muted">
                Uses the API on this machine. Your token stays in memory and is
                cleared on disconnect or reload.
              </p>
              <button className="primary" type="submit">
                Connect
              </button>
              <button
                type="button"
                onClick={() => {
                  setToken("");
                  setConnecting(false);
                }}
              >
                Cancel
              </button>
            </form>
          )}
          <Workspace key={generation} library={connection.library} />
          <footer>
            Saved text preserves its source revision. AI analysis is not
            available yet.
          </footer>
        </div>
      </main>
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
