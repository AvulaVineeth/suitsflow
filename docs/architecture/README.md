# SuitsFlow Architecture

This directory is the implementation contract for SuitsFlow. It describes the target architecture and the decisions that constrain code, infrastructure, and evaluation work. It does not imply that every capability has already been implemented.

## Reading order

1. [Product and system overview](01-high-level-design.md)
2. [Data architecture](02-data-architecture.md)
3. [PostgreSQL domain model](03-postgresql-domain-model.md)
4. [Relational schema design](04-relational-schema-design.md)
5. [Data integrity and lifecycle](05-database-integrity-and-lifecycle-rules.md)
6. [Application architecture](06-application-architecture.md)
7. [Agent architecture](07-agent-architecture.md)
8. [RAG architecture](08-rag-architecture.md)
9. [MCP tool architecture](09-mcp-tool-architecture.md)
10. [Security architecture](10-security-architecture.md)
11. [Reliability and governance](11-reliability-and-governance.md)
12. [Observability and evaluation](12-observability-and-evaluation.md)
13. [Deployment architecture](13-deployment-architecture.md)

## Non-negotiable invariants

- Every protected data operation has an explicit authenticated principal and tenant context.
- The LLM never decides authorization and never directly accesses persistence or cloud resources.
- Retrieved documents and model output are untrusted input.
- State-changing agent actions are authorized, validated, audited, and may require approval.
- Every agent run is traceable and measurable for quality, latency, and cost.

## Documentation conventions

- **Target** means an intentional future-state design.
- **Initial implementation** means the smallest version to build first.
- Cross-cutting decisions belong in the most specific document; other documents link to it rather than restating it.
- New irreversible decisions should be recorded as an ADR in `docs/decisions/`.
