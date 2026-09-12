# PostgreSQL Domain Model

## Scope

This document defines the business entities and relationships that the PostgreSQL model must represent. It is independent of SQLAlchemy implementation details. Column types, indexes, and constraints are specified in [relational schema design](04-relational-schema-design.md) and [data integrity and lifecycle](05-database-integrity-and-lifecycle-rules.md).

---

## 1. Start with the business domains

Instead of thinking about 20+ tables independently, group them into logical domains:

```text id="2j6r3m"
SuitsFlow
│
├── Identity & Access
│   ├── Tenant
│   ├── User
│   ├── Role
│   └── Permission
│
├── Document Management
│   ├── Document
│   ├── DocumentVersion
│   └── DocumentChunk
│
├── Legal Domain
│   ├── Contract
│   ├── ContractParty
│   ├── ContractClause
│   ├── Policy
│   └── PolicyRequirement
│
├── Compliance & Review
│   ├── Review
│   ├── RiskFinding
│   ├── Task
│   └── TaskAssignment
│
└── AI Execution
    ├── AgentRun
    ├── LLMCall
    ├── Retrieval
    ├── ToolCall
    ├── Approval
    └── AuditLog
```

This gives us a much cleaner mental model.

---

# 2. Tenant

`Tenant` represents an enterprise/customer using SuitsFlow.

```text id="l6z2wa"
Tenant
──────────────
id
name
status
created_at
updated_at
```

Example:

```text
Tenant
──────
1 | Acme Corporation
2 | Globex Corporation
3 | Initech
```

Every tenant-owned resource is associated with a tenant.

```text
Tenant
   │
   ├── Users
   ├── Documents
   ├── Contracts
   ├── Policies
   ├── Reviews
   ├── Tasks
   └── AgentRuns
```

### Important design decision

We are choosing **shared database / shared schema with `tenant_id` isolation** for the initial architecture.

That gives us:

* simpler operations
* lower infrastructure cost
* easier development
* straightforward relational queries

But it requires strong tenant isolation at the application and database layers.

We'll document the alternative models later.

---

# 3. User / Role / Permission

We don't want authorization logic embedded into individual endpoints.

Instead:

```text id="qv1p9j"
User
 │
 └── Role
       │
       └── Permission
```

### User

```text id="kq0g9x"
User
──────────────
id
tenant_id
email
name
status
created_at
updated_at
```

### Role

```text id="r2c8df"
Role
──────────────
id
tenant_id
name
description
```

Examples:

```text
LegalAdmin
LegalReviewer
ComplianceAnalyst
Employee
```

### Permission

```text id="5kz9mv"
Permission
──────────────
id
name
description
```

Examples:

```text
contract:read
contract:create
contract:update
review:read
review:create
task:create
task:assign
```

Then:

```text id="g3y3q8"
User
 │
 └── UserRole
        │
        ▼
       Role
        │
        └── RolePermission
                │
                ▼
            Permission
```

This is classic RBAC.

---

# 4. Document

Now we move into the legal data itself.

A `Document` represents the logical document.

```text id="1p55g4"
Document
──────────────
id
tenant_id
name
document_type
status
created_by
created_at
updated_at
```

Examples:

```text
Employment Agreement
Data Retention Policy
Vendor Contract
Privacy Policy
NDA
```

But here's an important distinction:

**Document ≠ Document Version**

A document may have multiple versions.

---

# 5. DocumentVersion

```text id="h9qg8s"
Document
   │
   ├── Version 1
   ├── Version 2
   └── Version 3
```

So:

```text id="4p1ggo"
DocumentVersion
──────────────
id
document_id
version_number
s3_key
mime_type
file_size
checksum
uploaded_by
created_at
```

For example:

```text
Document
id = 101

DocumentVersion
────────────────
v1 → s3://.../v1.pdf
v2 → s3://.../v2.pdf
v3 → s3://.../v3.pdf
```

This allows us to preserve document history.

---

# 6. DocumentChunk

The document is eventually broken into chunks for RAG.

```text id="8v0v5x"
Document
   │
   └── DocumentVersion
          │
          ├── Chunk 1
          ├── Chunk 2
          ├── Chunk 3
          └── ...
```

Conceptually:

```text id="3c8yqv"
DocumentChunk
──────────────
id
document_version_id
chunk_index
page_number
text_reference
metadata
created_at
```

We don't necessarily need to store the complete chunk text in PostgreSQL.

We can keep large extracted content in S3 and use PostgreSQL for metadata/reference information.

The vector layer then contains the embedding associated with the chunk.

---

# 7. Contract

Now we introduce the **domain-specific structured representation**.

A contract is not merely a PDF.

```text id="4m7dkw"
Contract
──────────────
id
tenant_id
document_id
contract_number
contract_type
status
effective_date
expiration_date
renewal_date
risk_level
created_at
updated_at
```

This allows queries such as:

> "Show me all contracts expiring within 90 days."

That query should **not require an LLM**.

It can simply be:

```text id="q8x0kg"
FastAPI
   ↓
MCP tool
   ↓
PostgreSQL
   ↓
Contracts
```

This is one of the reasons our structured domain model matters.

---

# 8. ContractParty

Contracts usually involve multiple parties.

```text id="1u2e9f"
Contract
   │
   ├── Party A
   ├── Party B
   └── Party C
```

We therefore have:

```text id="1q8z8k"
ContractParty
──────────────
id
contract_id
name
party_type
role
```

Example:

```text
Acme Corp       → customer
SuitsFlow Inc   → vendor
```

We can later normalize parties into their own entity if the business requirements justify it.

For the initial architecture, we don't need to over-engineer it.

---

# 9. ContractClause

Clauses are important because our AI system will reason about them.

```text id="n3a1xk"
Contract
   │
   └── ContractClause
          ├── Termination
          ├── Liability
          ├── Confidentiality
          ├── Data Protection
          └── Renewal
```

Conceptually:

```text id="s7j1qf"
ContractClause
──────────────
id
contract_id
document_chunk_id
clause_type
title
text_reference
risk_level
created_at
```

Notice the relationship:

```text
ContractClause
      │
      └── DocumentChunk
```

This connects the **structured legal domain** with the **unstructured RAG domain**.

That's an important architectural relationship.

---

# 10. Policy

A policy represents organizational rules.

```text id="m7p0wd"
Policy
──────────────
id
tenant_id
document_id
name
policy_type
status
effective_date
created_at
updated_at
```

Examples:

```text
Data Retention Policy
Access Control Policy
Vendor Security Policy
Privacy Policy
```

---

# 11. PolicyRequirement

A policy can contain multiple requirements.

```text id="h2k5r8"
Policy
 │
 ├── Requirement 1
 ├── Requirement 2
 ├── Requirement 3
 └── Requirement 4
```

Example:

```text
Data Retention Policy

Requirement:
Customer data must be deleted after 7 years.
```

Schema concept:

```text id="8sp3mu"
PolicyRequirement
──────────────
id
policy_id
requirement_type
description
severity
created_at
```

This becomes very useful for compliance analysis.

---

# 12. Review

A `Review` represents a legal/compliance review process.

```text id="4t6y8s"
Contract
    │
    ▼
Review
```

Conceptually:

```text id="v0x8re"
Review
──────────────
id
tenant_id
contract_id
review_type
status
requested_by
assigned_to
created_at
completed_at
```

Examples:

```textContract Compliance Review
Vendor Risk Review
Privacy Review
Security Review
```

---

# 13. RiskFinding

During a review, the AI may identify risks.

```text id="6m9w1x"
Review
  │
  ├── Risk Finding
  ├── Risk Finding
  └── Risk Finding
```

Conceptually:

```text id="d0j4vq"
RiskFinding
──────────────
id
review_id
contract_clause_id
risk_type
severity
description
recommendation
status
created_at
```

Example:

```text
Risk:
Unlimited liability exposure

Severity:
HIGH

Recommendation:
Request a liability cap.
```

This is where our AI analysis begins to become **structured enterprise data**.

---

# 14. Task

An AI agent should sometimes be able to turn analysis into an actionable workflow.

For example:

> "Create a legal review task for this high-risk contract."

We therefore have:

```text id="b7t1kc"
Task
──────────────
id
tenant_id
title
description
status
priority
created_by
due_date
created_at
updated_at
```

And:

```text id="h1d6k0"
TaskAssignment
──────────────
id
task_id
user_id
assigned_at
```

This creates our human-in-the-loop workflow.

---

# 15. AgentRun

Now we get to the AI architecture.

Every meaningful agent execution gets an `AgentRun`.

```text id="1k7v9r"
AgentRun
──────────────
id
tenant_id
user_id
conversation_id
workflow
status
model
prompt_version
started_at
completed_at
latency_ms
token_usage
estimated_cost
```

Example:

```text
AgentRun
────────────────────────────
workflow: contract_analysis
model: Claude
prompt_version: v3
status: completed
latency: 7.2 sec
tokens: 8,431
cost: $0.XX
```

This becomes extremely useful for observability and AI evaluation.

---

# 16. LLMCall

One agent run may involve multiple model calls.

```text id="c4e5yx"
AgentRun
   │
   ├── LLMCall
   ├── LLMCall
   └── LLMCall
```

Conceptually:

```text id="v4t3nb"
LLMCall
──────────────
id
agent_run_id
model
prompt_version
input_tokens
output_tokens
latency_ms
status
created_at
```

---

# 17. Retrieval

We also want to know what information the agent retrieved.

```text id="z5w8k3"
AgentRun
   │
   └── Retrieval
         ├── Chunk A
         ├── Chunk B
         └── Chunk C
```

Conceptually:

```text id="h4v2pr"
Retrieval
──────────────
id
agent_run_id
query
result_count
latency_ms
created_at
```

We can then associate retrieved chunks/results.

This will eventually allow us to evaluate:

> "Did the agent retrieve the right information?"

---

# 18. ToolCall

This becomes particularly important once we implement MCP.

```text id="r0x2k7"
AgentRun
   │
   ├── LLMCall
   │
   ├── Retrieval
   │
   └── ToolCall
          │
          ▼
       MCP Tool
```

Conceptually:

```text id="3c4t9v"
ToolCall
──────────────
id
agent_run_id
tool_name
arguments
result
status
latency_ms
created_at
```

For example:

```text
tool_name:
get_expiring_contracts

arguments:
{
    "days": 90
}
```

We should be careful with storing raw arguments/results because they may contain sensitive information. That becomes part of our later **Data Security** design.

---

# 19. Approval

State-changing AI actions require approval where appropriate.

```text id="8f1m2a"
AgentRun
   │
   └── Approval
```

Conceptually:

```text id="n6v0qd"
Approval
──────────────
id
tenant_id
agent_run_id
requested_by
approved_by
action_type
status
reason
created_at
resolved_at
```

Flow:

```text
Agent
  ↓
Proposes action
  ↓
Approval
  ↓
Human approves
  ↓
MCP tool
  ↓
Enterprise system
```

This is a major enterprise-AI design feature.

---

# 20. AuditLog

Finally, we need an audit trail.

```text id="e4n8kp"
AuditLog
──────────────
id
tenant_id
user_id
action
resource_type
resource_id
metadata
created_at
```

Examples:

```text
USER_LOGIN
DOCUMENT_UPLOADED
CONTRACT_UPDATED
AGENT_EXECUTED
TOOL_EXECUTED
APPROVAL_GRANTED
TASK_CREATED
```

This is separate from normal application logs.

### Important distinction

```text
Application logs
    → debugging / operations

Audit logs
    → security / compliance / accountability

AI traces
    → model / agent observability
```

We shouldn't mix these together.

---

# 21. Complete domain model

Putting everything together:

```text id="j5n2cx"
                         ┌──────────────┐
                         │    Tenant    │
                         └──────┬───────┘
                                │
       ┌────────────────────────┼────────────────────────┐
       │                        │                        │
       ▼                        ▼                        ▼
     Users                  Documents                 Contracts
       │                        │                        │
     Roles                 Versions                  Parties
       │                        │                        │
 Permissions                Chunks                   Clauses
                                │                        │
                                │                        │
                                └──────────┬─────────────┘
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
               ┌────────────────────┼────────────────────┐
               │                    │                    │
               ▼                    ▼                    ▼
            LLMCalls             Retrievals           ToolCalls
                                                         │
                                                         ▼
                                                      Approvals

                         AuditLog
```

This is now a solid **domain-level model**.

---

# 22. One important architectural principle

Notice something subtle about our design.

We have **two representations of knowledge**:

### Unstructured knowledge

```text
Document
   ↓
DocumentVersion
   ↓
DocumentChunk
   ↓
Embedding
   ↓
Vector Store
```

Used for:

> "What does the contract say about termination?"

### Structured knowledge

```text
Contract
   ↓
expiration_date
status
contract_type
risk_level
parties
clauses
```

Used for:

> "Which contracts expire in the next 90 days?"

These should **coexist**, not compete.

That gives SuitsFlow a much stronger architecture than a simple "upload PDF → vector DB → chatbot" project.

---

## Implementation handoff

Use this model to create SQLAlchemy entities and migrations only after applying the key, index, constraint, tenancy, and lifecycle rules in [relational schema design](04-relational-schema-design.md) and [data integrity and lifecycle](05-database-integrity-and-lifecycle-rules.md).
