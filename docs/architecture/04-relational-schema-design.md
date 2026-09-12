# Relational Schema Design

## Scope

This document translates the domain model into PostgreSQL table, key, and index conventions. The domain meaning of entities belongs in [the domain model](03-postgresql-domain-model.md); deletion, audit, and tenancy invariants belong in [data integrity and lifecycle](05-database-integrity-and-lifecycle-rules.md).

## 1. ID strategy — UUID

We'll use **UUIDs** for primary keys.

```text
Tenant.id          → UUID
User.id            → UUID
Document.id        → UUID
Contract.id        → UUID
AgentRun.id        → UUID
...
```

### Why?

SuitsFlow is a distributed application. UUIDs give us:

* globally unique identifiers
* safer IDs to expose through APIs
* easier distributed creation
* no need for a centralized integer sequence across services

For example:

```text
GET /contracts/8d5e2a1c-...
```

rather than:

```text
GET /contracts/123
```

We don't need to overstate this as a security mechanism—UUIDs are **not authorization**. Authorization still happens through tenant/resource checks.

---

# 2. Timestamp strategy

We'll standardize on:

```text
TIMESTAMP WITH TIME ZONE
```

and store timestamps in UTC.

Typical fields:

```text
created_at
updated_at
started_at
completed_at
deleted_at
```

Application code can convert UTC to the user's local timezone when displaying it.

This is particularly important for:

* contract expiration dates
* review deadlines
* agent executions
* audit logs
* task assignments

---

# 3. Tenant-aware indexing

This is one of the most important database design decisions.

Because most queries are tenant-scoped:

```sql
WHERE tenant_id = :tenant_id
```

we should frequently use indexes beginning with `tenant_id`.

For example:

```text id="4n1y0e"
contracts
────────────────────────
PRIMARY KEY (id)

INDEX (tenant_id)
INDEX (tenant_id, expiration_date)
INDEX (tenant_id, status)
```

This is better than blindly indexing every column.

For a query:

```sql
SELECT *
FROM contracts
WHERE tenant_id = ?
  AND expiration_date <= ?;
```

the composite index:

```text
(tenant_id, expiration_date)
```

is particularly useful.

---

# 4. JSONB vs normalized columns

This is an important senior-level decision.

We should **not put the entire domain model into JSONB**.

For example, this is bad:

```text
Contract
────────────────────
id
data JSONB
```

with:

```json
{
  "status": "active",
  "expiration_date": "...",
  "risk": "high"
}
```

Why?

We lose:

* strong schema
* relational constraints
* predictable querying
* useful indexes
* referential integrity

Instead:

```text
Contract
────────────────────
id
tenant_id
status
expiration_date
risk_level
...
metadata JSONB
```

Use normal columns for **known, queryable business attributes**.

Use JSONB for **flexible metadata**.

For example:

```json
{
  "source_system": "salesforce",
  "custom_fields": {
    "business_unit": "North America"
  }
}
```

So our rule is:

> **Structured business data → columns. Flexible metadata → JSONB.**

---

# 5. Tenant table

Conceptual schema:

```text
tenants
────────────────────────
id                  UUID PK
name                VARCHAR
status              VARCHAR
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ
```

Constraints:

```text
name NOT NULL
status NOT NULL
```

We may later add:

```text
slug
external_id
settings JSONB
```

if the application needs them.

---

# 6. User table

```text
users
────────────────────────
id                  UUID PK
tenant_id           UUID FK
email               VARCHAR
name                VARCHAR
status              VARCHAR
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ
```

Important constraint:

```text
UNIQUE (tenant_id, email)
```

Why composite uniqueness?

Because two different tenants could theoretically have:

```text
john@example.com
```

but the same user identity should not be duplicated **within one tenant**.

---

# 7. Roles and permissions

We'll use join tables.

```text
roles
────────────────
id
tenant_id
name
description
created_at
```

```text
permissions
────────────────
id
name
description
```

Then:

```text
user_roles
────────────────
user_id
role_id
```

and:

```text
role_permissions
────────────────
role_id
permission_id
```

Relationships:

```text
User
 │
 ▼
UserRole
 │
 ▼
Role
 │
 ▼
RolePermission
 │
 ▼
Permission
```

This keeps authorization flexible.

---

# 8. Documents

```text
documents
────────────────────────
id                  UUID PK
tenant_id           UUID FK
name                VARCHAR
document_type       VARCHAR
status              VARCHAR
created_by          UUID FK
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ
```

Potential statuses:

```text
UPLOADING
PROCESSING
READY
FAILED
ARCHIVED
```

The document itself doesn't contain the PDF.

The actual file lives in S3.

---

# 9. Document versions

```text
document_versions
────────────────────────
id                  UUID PK
document_id         UUID FK
version_number      INTEGER
s3_key              TEXT
mime_type           VARCHAR
file_size           BIGINT
checksum            VARCHAR
uploaded_by         UUID FK
created_at          TIMESTAMPTZ
```

Important constraint:

```text
UNIQUE (document_id, version_number)
```

So:

```text
Document A
 ├── v1
 ├── v2
 └── v3
```

can't accidentally have two `v2`s.

---

# 10. Document chunks

```text
document_chunks
────────────────────────
id                  UUID PK
document_version_id UUID FK
chunk_index         INTEGER
page_number         INTEGER
text_reference      TEXT
metadata             JSONB
created_at          TIMESTAMPTZ
```

Constraint:

```text
UNIQUE (document_version_id, chunk_index)
```

This gives us deterministic chunk ordering.

---

# 11. Contracts

```text
contracts
────────────────────────
id                  UUID PK
tenant_id           UUID FK
document_id         UUID FK
contract_number     VARCHAR
contract_type       VARCHAR
status              VARCHAR
effective_date      DATE
expiration_date     DATE
renewal_date        DATE
risk_level          VARCHAR
metadata            JSONB
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ
```

Useful indexes:

```text
(tenant_id, expiration_date)
(tenant_id, status)
(tenant_id, contract_type)
```

This supports queries such as:

> Find active vendor contracts expiring within 90 days.

without involving an LLM.

---

# 12. Contract parties

```text
contract_parties
────────────────────────
id                  UUID PK
contract_id         UUID FK
name                VARCHAR
party_type          VARCHAR
role                VARCHAR
```

Index:

```text
(contract_id)
```

Eventually, if SuitsFlow needs sophisticated party management, we could introduce:

```text
organizations
```

and reference them from contracts.

But we don't need that complexity yet.

---

# 13. Contract clauses

```text
contract_clauses
────────────────────────
id                  UUID PK
contract_id         UUID FK
document_chunk_id   UUID FK
clause_type         VARCHAR
title               VARCHAR
text_reference      TEXT
risk_level          VARCHAR
metadata            JSONB
created_at          TIMESTAMPTZ
```

This relationship is particularly valuable:

```text
Contract
   │
   ▼
ContractClause
   │
   ▼
DocumentChunk
```

It lets us connect:

**business meaning → actual source text**

which is essential for citations and explainability.

---

# 14. Policies

```text
policies
────────────────────────
id                  UUID PK
tenant_id           UUID FK
document_id         UUID FK
name                VARCHAR
policy_type         VARCHAR
status              VARCHAR
effective_date      DATE
metadata            JSONB
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ
```

And:

```text
policy_requirements
────────────────────────
id                  UUID PK
policy_id           UUID FK
requirement_type    VARCHAR
description         TEXT
severity            VARCHAR
created_at          TIMESTAMPTZ
```

---

# 15. Reviews

```text
reviews
────────────────────────
id                  UUID PK
tenant_id           UUID FK
contract_id         UUID FK
review_type         VARCHAR
status              VARCHAR
requested_by        UUID FK
assigned_to         UUID FK
created_at          TIMESTAMPTZ
completed_at        TIMESTAMPTZ
```

A review might be:

```text
Contract
   ↓
Compliance Review
   ↓
AI analysis
   ↓
Risk findings
   ↓
Human review
```

---

# 16. Risk findings

```text
risk_findings
────────────────────────
id                  UUID PK
review_id           UUID FK
contract_clause_id  UUID FK
risk_type           VARCHAR
severity             VARCHAR
description         TEXT
recommendation      TEXT
status               VARCHAR
created_at           TIMESTAMPTZ
```

This gives us a traceable chain:

```text
Review
 ↓
Risk Finding
 ↓
Contract Clause
 ↓
Document Chunk
 ↓
Original Document
```

That's a very strong design for an AI/legal system because an AI-generated finding can ultimately be traced back to the source material.

---

# 17. Tasks

```text
tasks
────────────────────────
id                  UUID PK
tenant_id           UUID FK
title               VARCHAR
description         TEXT
status               VARCHAR
priority             VARCHAR
created_by           UUID FK
due_date             TIMESTAMPTZ
created_at           TIMESTAMPTZ
updated_at           TIMESTAMPTZ
```

Assignments:

```text
task_assignments
────────────────────────
id                  UUID PK
task_id             UUID FK
user_id             UUID FK
assigned_at         TIMESTAMPTZ
```

---

# 18. Agent execution tables

Now we reach the AI-specific portion.

### AgentRun

```text
agent_runs
────────────────────────
id                  UUID PK
tenant_id           UUID FK
user_id             UUID FK
conversation_id     UUID
workflow             VARCHAR
status               VARCHAR
model                VARCHAR
prompt_version      VARCHAR
started_at           TIMESTAMPTZ
completed_at         TIMESTAMPTZ
latency_ms           INTEGER
input_tokens        INTEGER
output_tokens       INTEGER
estimated_cost      NUMERIC
error_code          VARCHAR
metadata             JSONB
```

This is our AI execution record.

---

# 19. LLM calls

```text
llm_calls
────────────────────────
id                  UUID PK
agent_run_id        UUID FK
model               VARCHAR
prompt_version      VARCHAR
input_tokens        INTEGER
output_tokens       INTEGER
latency_ms          INTEGER
status              VARCHAR
created_at          TIMESTAMPTZ
metadata            JSONB
```

One `AgentRun` can have multiple `LLMCall`s.

```text
AgentRun
 ├── LLMCall
 ├── LLMCall
 └── LLMCall
```

---

# 20. Retrieval records

```text
retrievals
────────────────────────
id                  UUID PK
agent_run_id        UUID FK
query               TEXT
result_count        INTEGER
latency_ms          INTEGER
created_at          TIMESTAMPTZ
metadata            JSONB
```

We can associate retrieved chunks separately.

This will eventually support our evaluation system.

---

# 21. Tool calls

```text
tool_calls
────────────────────────
id                  UUID PK
agent_run_id        UUID FK
tool_name           VARCHAR
arguments            JSONB
result               JSONB
status               VARCHAR
latency_ms           INTEGER
created_at           TIMESTAMPTZ
```

This is particularly useful for MCP.

For example:

```text
AgentRun
   ↓
ToolCall
   ↓
get_expiring_contracts
   ↓
PostgreSQL
```

---

# 22. Approvals

```text
approvals
────────────────────────
id                  UUID PK
tenant_id           UUID FK
agent_run_id        UUID FK
action_type         VARCHAR
status              VARCHAR
requested_by        UUID FK
approved_by         UUID FK
reason              TEXT
created_at           TIMESTAMPTZ
resolved_at          TIMESTAMPTZ
```

Potential statuses:

```text
PENDING
APPROVED
REJECTED
EXPIRED
```

---

# 23. Audit logs

```text
audit_logs
────────────────────────
id                  UUID PK
tenant_id           UUID FK
user_id             UUID FK
action               VARCHAR
resource_type       VARCHAR
resource_id         UUID
metadata             JSONB
created_at           TIMESTAMPTZ
```

We'll eventually define which actions **must** generate audit events.

---

# 24. Complete relationship map

Now our model looks like this:

```text
                              Tenant
                                │
               ┌────────────────┼────────────────┐
               │                │                │
               ▼                ▼                ▼
             Users          Documents         Contracts
               │                │                │
             Roles          Versions          Parties
               │                │                │
         Permissions         Chunks           Clauses
                                │                │
                                └───────┬────────┘
                                        │
                                        ▼
                                      Reviews
                                        │
                                        ▼
                                  Risk Findings
                                        │
                                        ▼
                                      Tasks


                       ┌─────────────────────┐
                       │      AgentRun       │
                       └──────────┬──────────┘
                                  │
             ┌────────────────────┼─────────────────┐
             │                    │                 │
             ▼                    ▼                 ▼
          LLMCalls            Retrievals         ToolCalls
                                                    │
                                                    ▼
                                                 Approvals

                       AuditLogs
```

---

# 25. The most important design decision

There is a deeper architecture principle here:

```text
                    SuitsFlow Data
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
   Domain Truth      Knowledge Truth     AI Truth
        │                 │                 │
   PostgreSQL             S3             AgentRun
   Contracts            Documents        LLMCalls
   Reviews              Chunks           ToolCalls
   Tasks                Embeddings       Retrievals
   Users                                  Approvals
```

The **LLM doesn't become the source of truth**.

It analyzes information from these systems and produces decisions/recommendations/actions that are then validated and persisted through controlled application workflows.
---
