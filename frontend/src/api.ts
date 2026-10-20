export type Document = {
  id: string;
  name: string;
  document_type: string;
  created_at: string;
};
export type Revision = {
  id: string;
  document_id: string;
  version_number: number;
  mime_type: string;
  file_size: number;
  checksum: string;
  created_at: string;
  content_status:
    "pending_upload" | "pending_scan" | "clean" | "rejected" | "scan_failed";
};
export type Job = {
  status: "pending" | "running" | "completed" | "failed";
  attempts: number;
};
export type Extraction = {
  text: string;
  extractor: string;
  character_count: number;
  source_checksum: string;
};
export interface Library {
  documents(offset: number, signal: AbortSignal): Promise<Document[]>;
  revisions(
    id: string,
    offset: number,
    signal: AbortSignal,
  ): Promise<Revision[]>;
  job(
    document: string,
    version: string,
    kind: "scan" | "extraction",
    signal: AbortSignal,
  ): Promise<Job | null>;
  text(
    document: string,
    version: string,
    signal: AbortSignal,
  ): Promise<Extraction | null>;
}
export const PAGE_SIZE = 20;
export class ApiError extends Error {}
export function apiLibrary(token: string): Library {
  async function read<T>(
    path: string,
    signal: AbortSignal,
    optional = false,
  ): Promise<T> {
    const response = await fetch(`/api/v1/documents${path}`, {
      signal,
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      referrerPolicy: "no-referrer",
    });
    if (optional && response.status === 404) return null as T;
    if (!response.ok) {
      const message =
        response.status === 401
          ? "Your session is not authorized. Disconnect and reconnect with a valid token."
          : response.status === 403
            ? "You do not have permission to view this content."
            : response.status === 409
              ? "This revision has not been cleared for reading."
              : response.status === 404
                ? "This document is no longer available."
                : "The service is unavailable. Try refreshing shortly.";
      throw new ApiError(message);
    }
    return response.json() as Promise<T>;
  }
  const revisionPath = (document: string, version: string) =>
    `/${encodeURIComponent(document)}/versions/${encodeURIComponent(version)}`;
  return {
    documents: (offset, signal) =>
      read(`?limit=${PAGE_SIZE}&offset=${offset}`, signal),
    revisions: (id, offset, signal) =>
      read(
        `/${encodeURIComponent(id)}/versions?limit=${PAGE_SIZE}&offset=${offset}`,
        signal,
      ),
    job: (document, version, kind, signal) =>
      read(`${revisionPath(document, version)}/${kind}-job`, signal, true),
    text: (document, version, signal) =>
      read(`${revisionPath(document, version)}/extraction`, signal, true),
  };
}
