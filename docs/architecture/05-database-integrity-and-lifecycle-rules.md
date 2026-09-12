# Data Integrity and Lifecycle Rules

## Scope

This document defines invariants PostgreSQL must enforce: relationships, deletion behavior, uniqueness, concurrency, tenant isolation, and audit retention. It supplements—not replaces—the entity definitions in [the domain model](03-postgresql-domain-model.md) and physical design in [schema design](04-relational-schema-design.md).

## 1. Foreign-key strategy

Every relationship we identified should be enforced by the database where practical.

For example:

```text id="w3h8aj"
contracts.document_id
        │
        ▼
documents.id
```

So PostgreSQL prevents a contract from referencing a document that doesn't exist.

Similarly:

```text id="r7m3qk"
risk_findings.review_id
        ↓
reviews.id

risk_findings.contract_clause_id
        ↓
contract_clauses.id
```

This is important because application validation alone isn't enough. The database should protect its own integrity.

---

# 2. `ON DELETE` behavior

We should **not use `CASCADE` everywhere**.

This is an important architectural decision.

Consider:

```text
Tenant
  ↓
Contract
  ↓
Review
  ↓
RiskFinding
```

If someone accidentally deletes a tenant, we don't want an enormous cascade silently deleting everything.

Instead, we should distinguish between different relationships.

### Example

For a document version:

```text
Document
   ↓
DocumentVersion
```

A version belongs entirely to its document.

A cascade may be reasonable here.

But for:

```text
User
   ↓
AuditLog
```

we should **not cascade-delete audit history**.

So our general rule becomes:

> **Cascade only for tightly owned child records where deleting the parent logically means deleting the child. Preserve historical and compliance-sensitive records.**

---

# 3. Soft delete vs hard delete

This is another important decision.

We don't want to physically delete every business record immediately.

For entities such as:

```text
Document
Contract
Policy
User
Task
```

we can consider:

```text id="r8h7e2"
deleted_at
```

instead of immediately removing the row.

Example:

```text id="v1h4jw"
documents
────────────────
id
name
status
deleted_at
```

If:

```text
deleted_at IS NULL
```

the record is active.

If:

```text
deleted_at IS NOT NULL
```

the record has been logically deleted.

### Why?

It provides:

* recovery
* auditability
* safer accidental deletion handling
* better historical traceability

But we shouldn't blindly soft-delete everything.

---

# 4. Append-only data

Some records should essentially be **append-only**.

The most obvious examples are:

```text
AuditLog
LLMCall
ToolCall
Retrieval
```

For example:

```text id="yq8l6n"
AgentRun
   │
   ├── LLMCall
   ├── ToolCall
   └── Retrieval
```

Once an execution happened, we shouldn't modify its historical record to make it look different.

Instead of:

```text
ToolCall.status
FAILED → SUCCESS
```

after the fact, we should preserve what actually happened.

If a retry occurs:

```text id="yq3w8k"
ToolCall #1 → FAILED
ToolCall #2 → SUCCESS
```

Both remain part of the execution history.

This becomes extremely valuable for debugging AI behavior.

---

# 5. Audit logs should be immutable

`AuditLog` deserves special treatment.

```text id="w4j7m8"
AuditLog
──────────────
WHO
WHAT
RESOURCE
WHEN
METADATA
```

Example:

```text
user:       abc
action:     APPROVAL_GRANTED
resource:   review-123
timestamp:  ...
```

Once written, the application should not provide a normal update/delete operation for audit logs.

This supports:

> "Show me exactly what happened."

rather than:

> "Show me what the database currently says happened."

Those are very different things.

---

# 6. Unique constraints

We should use database constraints to prevent duplicate logical records.

Examples:

### Users

```text
UNIQUE (tenant_id, email)
```

### Document versions

```text
UNIQUE (document_id, version_number)
```

### Document chunks

```text
UNIQUE (document_version_id, chunk_index)
```

### Roles

Potentially:

```text
UNIQUE (tenant_id, name)
```

### Permissions

```text
UNIQUE (name)
```

These constraints protect us even if two API requests arrive simultaneously.

---

# 7. Check constraints

We can also let PostgreSQL reject invalid states.

For example, a contract's expiration date shouldn't precede its effective date.

Conceptually:

```sql id="8i0d5f"
CHECK (
    expiration_date IS NULL
    OR effective_date IS NULL
    OR expiration_date >= effective_date
)
```

Similarly, we can constrain values such as:

```text id="x5p8x0"
risk_level ∈ {LOW, MEDIUM, HIGH, CRITICAL}

status ∈ {DRAFT, ACTIVE, EXPIRED, ARCHIVED}
```

We should decide carefully whether to use PostgreSQL enums or application-level strings/check constraints.

For the first implementation, I recommend **strings + application enums + database check constraints where the invariant is important**.

Why?

It keeps schema migrations less rigid than PostgreSQL native enums while still protecting critical values.

---

# 8. Index strategy

We shouldn't create indexes on every column.

Every index has a cost:

```text
More indexes
   ↓
Faster reads
   +
More storage
   +
Slower writes
   +
More maintenance
```

So indexes should follow actual query patterns.

### High-value examples

Contracts:

```text
(tenant_id, expiration_date)
(tenant_id, status)
```

Documents:

```text
(tenant_id, status)
(tenant_id, document_type)
```

Reviews:

```text
(tenant_id, status)
(tenant_id, assigned_to)
```

Tasks:

```text
(tenant_id, status)
(tenant_id, due_date)
```

Agent runs:

```text
(tenant_id, created_at)
(tenant_id, status)
```

Audit logs:

```text
(tenant_id, created_at)
(tenant_id, resource_type, resource_id)
```

Notice the recurring pattern:

```text
tenant_id + query/filter column
```

because tenant-scoped queries are fundamental to our architecture.

---

# 9. Optimistic concurrency

Suppose two legal reviewers open the same contract.

```text id="3g3y1b"
Reviewer A ──┐
             ├── Contract
Reviewer B ──┘
```

Both read version 5.

Reviewer A updates it.

```text
v5 → v6
```

Reviewer B then submits an update based on stale version 5.

We don't want B to accidentally overwrite A's changes.

A simple approach is a version column:

```text id="8e1u9c"
Contract
──────────────
id
...
version
updated_at
```

Update conceptually becomes:

```sql id="l5z07v"
UPDATE contracts
SET ...
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
```

If zero rows are updated, the client had a stale version.

This is **optimistic concurrency control**.

We don't necessarily need it on every table. It makes the most sense for important mutable resources such as:

```text Contract
Review
Task
Document metadata
```

---

# 10. Tenant isolation

This is critical enough to deserve multiple layers.

Our architecture should be:

```text id="m4e7cy"
                    Request
                       │
                       ▼
                  JWT/OAuth
                       │
                       ▼
                 User Identity
                       │
                       ▼
                  tenant_id
                       │
                       ▼
                 Authorization
                       │
                       ▼
              FastAPI Repository
                       │
                       ▼
                  PostgreSQL
                       │
                       ▼
             Tenant-scoped query
```

For example:

```sql id="7qu7b5"
SELECT *
FROM contracts
WHERE tenant_id = :tenant_id
  AND id = :contract_id;
```

We should **never** have:

```sql id="5n3p1s"
SELECT *
FROM contracts
WHERE id = :contract_id;
```

without subsequently validating tenant ownership.

---

# 11. PostgreSQL Row-Level Security

We can add another layer using PostgreSQL RLS.

Conceptually:

```text id="n0y7qf"
Application authorization
        +
PostgreSQL RLS
        ↓
Defense in depth
```

RLS can enforce:

> A database session can only access rows belonging to its current tenant context.

However, there's an implementation consideration: connection pooling and setting tenant context safely.

Therefore, we shouldn't blindly turn on RLS before understanding our SQLAlchemy connection/session architecture.

We'll design this when we implement the security architecture.

For now:

**Decision:** application-level tenant isolation is mandatory; PostgreSQL RLS is a planned defense-in-depth layer.

---

# 12. Deletion behavior by entity

Here's a practical first-pass policy:

| Entity            | Delete strategy                             |
| ----------------- | ------------------------------------------- |
| Tenant            | Restricted / administrative lifecycle       |
| User              | Soft delete / deactivate                    |
| Role              | Soft delete or restricted                   |
| Permission        | Restricted                                  |
| Document          | Soft delete                                 |
| DocumentVersion   | Usually retained                            |
| DocumentChunk     | Rebuilt/replaced with processing            |
| Contract          | Soft delete/archive                         |
| ContractParty     | Can cascade with contract where appropriate |
| ContractClause    | Derived data; can be replaced               |
| Policy            | Archive                                     |
| PolicyRequirement | Can be replaced with policy version         |
| Review            | Retain                                      |
| RiskFinding       | Retain                                      |
| Task              | Retain                                      |
| AgentRun          | Retain                                      |
| LLMCall           | Retain according to retention policy        |
| Retrieval         | Retain according to AI telemetry policy     |
| ToolCall          | Retain                                      |
| Approval          | Retain                                      |
| AuditLog          | Append-only                                 |

This will later feed directly into **Data Lifecycle**.

---

# 13. One refinement: document processing

There's an important issue with `DocumentChunk`.

Imagine:

```text
Contract v1
   ↓
Chunks
```

Then the document gets reprocessed.

We shouldn't accidentally mix:

```text
v1 chunks
```

with:

```text
v2 chunks
```

Our relationship already protects us:

```text
Document
 ├── Version 1
 │     ├── Chunk 1
 │     └── Chunk 2
 │
 └── Version 2
       ├── Chunk 1
       └── Chunk 2
```

This means embeddings can also be associated with a specific document version.

That's important for RAG correctness.

---

# 14. Derived vs authoritative data

Another useful distinction:

### Authoritative

```text
Contract.expiration_date
Contract.status
Review.status
Task.status
```

These are business truth.

### Derived

```text
DocumentChunk
Embedding
RiskFinding
Retrieval result
AI-generated classification
```

Some of these are derived from source material.

This means we should be able to **rebuild derived data** when necessary.

For example:

```text
DocumentVersion
      ↓
reprocess
      ↓
new chunks
      ↓
new embeddings
```

We shouldn't make the vector index the only place where knowledge exists.

---

# 15. Our database philosophy

At this point, we can summarize our relational database rules:

```text id="p9cv8s"
1. PostgreSQL is the system of record for structured domain data.

2. Every tenant-owned resource is tenant-scoped.

3. Foreign keys enforce relationships.

4. Unique constraints prevent duplicate logical records.

5. Indexes follow real query patterns.

6. JSONB is used for flexible metadata, not core business fields.

7. Historical AI/audit records are retained and treated as append-only.

8. Soft deletion is preferred for recoverable business entities.

9. Derived AI/RAG data can be regenerated.

10. Authorization is enforced outside the LLM.

11. Tenant isolation exists at the application layer, with RLS considered
    as defense in depth.

12. Optimistic concurrency protects important mutable resources.
```

This is now a fairly mature database architecture.

---

## Implementation handoff

Migrations must encode these rules wherever PostgreSQL can enforce them. Application services add authorization and workflow policy, but must not weaken database-level tenant, relationship, uniqueness, or audit guarantees.
