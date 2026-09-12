# Data Architecture

## Scope

This document assigns each data type to an authoritative store and describes its lifecycle. The domain entities are defined in [the domain model](03-postgresql-domain-model.md); relational details are defined in [schema design](04-relational-schema-design.md). Security and retrieval-specific controls are canonical in [security](10-security-architecture.md) and [RAG architecture](08-rag-architecture.md).

## 1. Data architecture goals

SuitsFlow has several fundamentally different kinds of data, so **we should not try to put everything into PostgreSQL**.

The key principle is:

> **Store each type of data in the system that is best suited for its access pattern, consistency requirements, and lifecycle.**

Our initial data-storage model is:

| Data                     | Storage               | Why                         |
| ------------------------ | --------------------- | --------------------------- |
| Users, tenants, roles    | PostgreSQL            | Relational + transactional  |
| Contracts & metadata     | PostgreSQL            | Structured queries          |
| Contract clauses         | PostgreSQL            | Relational/domain queries   |
| Policies & requirements  | PostgreSQL            | Structured relationships    |
| Reviews & risk findings  | PostgreSQL            | Transactional workflow data |
| Tasks & assignments      | PostgreSQL            | Transactional state         |
| Documents/PDFs           | S3                    | Large immutable objects     |
| Extracted document text  | S3                    | Large unstructured data     |
| Embeddings               | Vector store          | Similarity search           |
| Agent/workflow state     | PostgreSQL / DynamoDB | Durable workflow state      |
| Short-lived cache        | Redis                 | Fast temporary access       |
| Agent/tool/audit records | PostgreSQL            | Queryable audit trail       |
| Application logs         | CloudWatch            | Operational logging         |
| LLM traces               | Langfuse              | AI observability            |

---

# 2. Overall data architecture

```text
                         ┌─────────────────────┐
                         │      SuitsFlow      │
                         │                     │
                         │   FastAPI / Agents  │
                         └──────────┬──────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
       ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
       │ PostgreSQL   │      │     S3       │      │ Vector Store │
       │              │      │              │      │              │
       │ Domain data  │      │ Documents    │      │ Embeddings   │
       │ Transactions │      │ Versions     │      │ Chunks       │
       │ Users        │      │ Raw files    │      │              │
       │ Contracts    │      │ Extracted    │      │ Semantic     │
       │ Reviews      │      │ text         │      │ retrieval    │
       └──────────────┘      └──────────────┘      └──────────────┘
              │                     │                     │
              │                     │                     │
              └──────────────┬──────┴─────────────────────┘
                             │
                    ┌────────▼────────┐
                    │     Redis       │
                    │                 │
                    │ Cache           │
                    │ Sessions/state  │
                    │ Rate limiting   │
                    └─────────────────┘

                    ┌─────────────────┐
                    │    DynamoDB     │
                    │                 │
                    │ Agent/workflow  │
                    │ state when      │
                    │ appropriate     │
                    └─────────────────┘
```

But there's an important decision we need to make here.

## 3. PostgreSQL vs DynamoDB for agent state

### PostgreSQL

Use PostgreSQL as the **system of record for business/domain data**.

For example:

```text
Tenant
User
Role
Permission
Document
Contract
ContractParty
ContractClause
Policy
PolicyRequirement
Review
RiskFinding
Task
Approval
AuditLog
AgentRun
ToolCall
```

These entities have relationships.

For example:

```text
Tenant
  │
  ├── Users
  │
  ├── Contracts
  │     └── Clauses
  │
  ├── Policies
  │     └── Requirements
  │
  └── Reviews
        ├── Findings
        └── Tasks
```

PostgreSQL is naturally suited for this.

---

### DynamoDB

We can introduce DynamoDB **specifically for high-scale, durable workflow/agent state** if our implementation actually benefits from it.

For example:

```text
workflow_id
    ↓
agent execution state
    ↓
current node
    ↓
checkpoint
    ↓
retry metadata
    ↓
execution status
```

This gives us a meaningful discussion:

> "PostgreSQL is the transactional source of truth for our legal domain. DynamoDB is used selectively for high-throughput workflow/checkpoint state where key-value access and horizontal scalability are more appropriate."

If we later determine that PostgreSQL is sufficient for the initial implementation, that's also a valid architectural decision.

---

# 4. S3 — document storage

We should **never store PDFs/documents directly inside PostgreSQL**.

Instead:

```text
User
 ↓
POST /documents
 ↓
FastAPI
 ↓
S3
```

PostgreSQL stores metadata:

```text
Document
──────────────
id
tenant_id
name
document_type
version
s3_key
mime_type
size
checksum
created_at
```

S3 stores:

```text
documents/
    tenant-123/
        contracts/
            contract-456/
                v1/
                    original.pdf
                v2/
                    original.pdf
```

This gives us:

* scalable object storage
* versioning
* encryption
* lifecycle management
* separation between metadata and binary content

---

# 5. Document processing architecture

When a user uploads a contract:

```text
                  Upload
                     │
                     ▼
                ┌─────────┐
                │ FastAPI │
                └────┬────┘
                     │
              Store metadata
                     │
                     ▼
                PostgreSQL
                     │
                     │
                     ▼
                     S3
                original.pdf
                     │
                     ▼
                  Event
                     │
                     ▼
                   Queue
                     │
                     ▼
              Document Worker
                     │
           ┌─────────┼─────────┐
           ▼         ▼         ▼
        Extract    Chunk     Metadata
           │         │
           └────┬────┘
                ▼
           Generate
          embeddings
                │
                ▼
          Vector Store
```

This is intentionally asynchronous.

We don't want:

```text
POST /documents

wait 30 seconds...

"Upload successful"
```

Instead:

```text
POST /documents
       ↓
202 Accepted
       ↓
processing
       ↓
completed
```

That gives us a good opportunity to demonstrate:

* asynchronous processing
* queues
* retries
* idempotency
* dead-letter queues
* eventual consistency

---

# 6. Vector storage

The vector layer should contain **retrieval-oriented representations**, not become our source of truth.

Conceptually:

```text
PostgreSQL
     │
     │ document/chunk metadata
     │
     ▼
DocumentChunk
     │
     ├── document_id
     ├── tenant_id
     ├── permissions
     ├── page_number
     ├── chunk_index
     └── text reference
     
     │
     ▼
Embedding
     │
     ▼
Vector Store
```

A vector record might conceptually contain:

```text
chunk_id
document_id
tenant_id
embedding
metadata
```

The important security point:

> **Tenant and authorization filters must be applied during retrieval.**

We should never retrieve everything and then ask the LLM:

> "Which documents is this user allowed to see?"

The application controls authorization.

---

# 7. Redis

Redis should be used for **short-lived, high-speed data**, not permanent business data.

Potential uses:

```text
Redis
 ├── API rate limiting
 ├── response caching
 ├── session-related ephemeral state
 ├── frequently accessed metadata
 └── temporary coordination
```

For example:

```text
GET /policies/data-retention

FastAPI
   ↓
Redis?
   ├── HIT → return cached result
   │
   └── MISS
         ↓
      PostgreSQL
         ↓
       Redis
         ↓
      response
```

We should avoid putting authoritative contract/review/task information only in Redis.

---

# 8. Core domain model

Now we can start deriving the PostgreSQL schema.

At the highest level:

```text
Tenant
 │
 ├── Users
 │    └── Roles
 │         └── Permissions
 │
 ├── Documents
 │    └── DocumentVersions
 │         └── DocumentChunks
 │
 ├── Contracts
 │    ├── ContractParties
 │    └── ContractClauses
 │
 ├── Policies
 │    └── PolicyRequirements
 │
 ├── Reviews
 │    └── RiskFindings
 │
 ├── Tasks
 │    └── TaskAssignments
 │
 └── AgentRuns
      ├── LLMCalls
      ├── Retrievals
      ├── ToolCalls
      ├── Approvals
      └── AuditLogs
```

This is the foundation we'll refine.

---

# 9. Multi-tenancy

Because this is an **enterprise platform**, multi-tenancy needs to be part of the architecture from the beginning.

Most tenant-owned tables should contain:

```text
tenant_id
```

For example:

```text
contracts
──────────────
id
tenant_id
name
status
start_date
end_date
...
```

A request should establish tenant context:

```text
JWT
 │
 ├── user_id
 ├── tenant_id
 └── roles
       │
       ▼
FastAPI
       │
       ▼
Authorization
       │
       ▼
Database query
```

Conceptually:

```sql
SELECT *
FROM contracts
WHERE tenant_id = :current_tenant;
```

We should eventually consider PostgreSQL Row-Level Security as an additional defense-in-depth mechanism.

---

# 10. Authorization vs authentication

This distinction will be important throughout SuitsFlow.

```text
Authentication
     ↓
"Who are you?"
     ↓
JWT / OAuth
```

versus:

```text
Authorization
     ↓
"What are you allowed to do?"
     ↓
RBAC + resource permissions
```

And critically:

```text
LLM
 ❌ determines authorization

FastAPI / authorization layer
 ✅ determines authorization
```

Same principle applies to MCP.

```text
Agent
  ↓
MCP tool request
  ↓
Authorization
  ↓
Business logic
  ↓
Repository
  ↓
Database
```

---

# 11. Agent execution data

This is an important part of the architecture because SuitsFlow is not merely a RAG application.

Every meaningful AI execution should have an `AgentRun`.

Conceptually:

```text
AgentRun
──────────────
id
tenant_id
user_id
conversation_id
workflow
model
prompt_version
status
started_at
completed_at
latency_ms
token_usage
estimated_cost
```

Then:

```text
AgentRun
   │
   ├── LLMCall
   │
   ├── Retrieval
   │
   ├── ToolCall
   │
   ├── Approval
   │
   └── Evaluation
```

This makes each run explainable: what was retrieved, which tools were considered or executed, and how the final outcome was reached.

---

## 12. Data security

Protect data at rest and in transit, scope it by tenant and resource policy before retrieval, and keep credentials outside source control. [Security architecture](10-security-architecture.md) is the canonical control specification.

## 13. Data lifecycle

Original documents, transactional records, and audit records are authoritative data with independent retention requirements. Chunks, embeddings, and indexes are derived data and may be rebuilt from a document version. Deletion and retention semantics are defined in [data integrity and lifecycle](05-database-integrity-and-lifecycle-rules.md).

## 14. Data-flow summary

Document ingestion flows from object storage to extracted text, versioned chunks, embeddings, and a retrieval index. A user request flows from authenticated context through either tenant-filtered retrieval or an authorized tool, then into an auditable agent run.

## 15. Trade-offs

PostgreSQL is the system of record for transactional domains and audit queries; S3 holds large immutable artifacts; Redis serves short-lived access patterns. DynamoDB and a separate vector service are target components when workload scale or access patterns justify their operational cost.

## 16. Implementation handoff

Start locally with PostgreSQL, an S3-compatible object store, and a vector capability with strict metadata filtering. Introduce additional stores only with a measured use case and an ADR.
