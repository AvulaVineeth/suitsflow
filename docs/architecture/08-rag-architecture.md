# RAG Architecture

## Goal

Provide source-grounded answers from documents the caller is authorized to read. RAG is not used for authoritative structured facts such as expiration dates when a transactional tool is available.

## Ingestion pipeline

```text
Upload → malware/type validation → immutable object storage
       → text extraction → normalization → chunking → embeddings → index
       → metadata and processing status persisted
```

Documents retain versions. Chunks, embeddings, and indexes are derived data and can be regenerated from the authoritative document version.

## Retrieval pipeline

```text
Query → tenant + ACL filter → lexical/vector retrieval → rerank
      → context assembly → model → answer with citations
```

Authorization filtering occurs before candidates reach the model. Metadata must include tenant, document/version identifiers, document type, and applicable access scope.

## Context and citations

Context is supplied as clearly delimited, untrusted reference material. The response cites the document version and chunk or clause that supports each material claim. Missing evidence must result in an uncertainty response, not an invented citation.

## Initial implementation

Start with versioned policy documents, deterministic chunking, metadata-filtered vector search, and direct citations. Add hybrid search, reranking, and query transformation only when an evaluation dataset establishes a need.
