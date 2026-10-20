import type { Document, Library, Revision } from "./api";

const sampleText =
  "MASTER SERVICES AGREEMENT\n\nSample content for exploring SuitsFlow.\n\n1. Scope of services\nThe parties agree to the services described in each statement of work.\n\n2. Confidentiality\nEach party will protect confidential information received from the other party.";
const date = "2026-10-20T09:00:00Z";
const documents: Document[] = [
  {
    id: "sample-contract",
    name: "Master services agreement",
    document_type: "contract",
    created_at: date,
  },
  {
    id: "sample-policy",
    name: "Information security policy",
    document_type: "policy",
    created_at: date,
  },
  {
    id: "sample-nda",
    name: "Mutual non-disclosure agreement",
    document_type: "contract",
    created_at: date,
  },
];
const revision = (
  document_id: string,
  version_number: number,
  content_status: Revision["content_status"],
): Revision => ({
  id: `${document_id}-${version_number}`,
  document_id,
  version_number,
  content_status,
  mime_type: "text/plain",
  file_size: 842,
  checksum: "a".repeat(64),
  created_at: date,
});
const revisions = [
  revision("sample-contract", 2, "clean"),
  revision("sample-contract", 1, "clean"),
  revision("sample-policy", 1, "pending_scan"),
  revision("sample-nda", 1, "pending_upload"),
];
export const sampleLibrary: Library = {
  documents: async (offset) => documents.slice(offset, offset + 20),
  revisions: async (id, offset) =>
    revisions
      .filter((row) => row.document_id === id)
      .slice(offset, offset + 20),
  job: async (document, _version, kind) =>
    document === "sample-contract"
      ? { status: "completed", attempts: 1 }
      : document === "sample-policy" && kind === "scan"
        ? { status: "pending", attempts: 0 }
        : null,
  text: async () => ({
    extractor: "plain-text-v1",
    character_count: sampleText.length,
    source_checksum: "a".repeat(64),
    text: sampleText,
  }),
};
