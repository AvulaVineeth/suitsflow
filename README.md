# ⚖️ SuitsFlow

### Enterprise Legal & Compliance AI Platform

**SuitsFlow** is a production-oriented AI platform designed to help legal and compliance teams analyze contracts, retrieve enterprise knowledge, identify risks, and automate controlled workflows using **LLM-powered agents, RAG, and MCP**.

The project is built to demonstrate how modern GenAI systems can be engineered beyond a simple chatbot — with **security, authorization, observability, evaluation, reliability, infrastructure-as-code, and human-in-the-loop controls** treated as first-class architectural concerns.

> **The goal:** Build an enterprise-grade AI agent platform that can reason over legal knowledge, securely interact with enterprise systems, and execute controlled workflows while remaining observable, evaluatable, and governable.

---

## 🚀 Why SuitsFlow?

Enterprise AI applications have challenges that go far beyond calling an LLM.

A production system needs to answer questions such as:

* How does an agent access enterprise data safely?
* When should the system use RAG versus structured data?
* How are tool calls authorized?
* How do we prevent retrieved documents from becoming malicious instructions?
* How do we evaluate whether an agent's answer is actually correct?
* How do we observe LLM latency, token usage, cost, and failures?
* How do we recover from failed multi-step workflows?
* How do we safely allow an AI system to perform actions?
* How do we introduce human approval for high-impact decisions?
* How do we deploy and reproduce the entire platform through infrastructure-as-code?

SuitsFlow is designed around these questions.

---

# 🧠 Core Capabilities

### 📄 Enterprise Document Intelligence

* Contract and policy ingestion
* Document versioning
* Document metadata
* Text extraction and chunking
* Embedding generation
* Semantic and hybrid retrieval
* Source-grounded responses
* Citation generation

### 🤖 AI Agent Workflows

Built with **LangGraph** and **Amazon Bedrock** to support stateful workflows such as:

* Contract analysis
* Compliance reviews
* Legal risk identification
* Enterprise knowledge Q&A
* Contract expiration analysis
* Legal review workflows

### 🔌 MCP Enterprise Tool Layer

SuitsFlow uses **Model Context Protocol (MCP)** to expose controlled enterprise capabilities to AI agents.

Example tools:

```text
search_contracts()
get_contract()
get_contract_clauses()
get_expiring_contracts()

search_policies()
get_policy()
check_compliance_requirement()

create_review_task()
assign_reviewer()
update_review_status()
```

The agent does **not** directly access databases or internal services.

Instead:

```text
Agent
   ↓
MCP Tool
   ↓
Authorization
   ↓
Business Logic
   ↓
Repository
   ↓
Enterprise Data
```

This provides a clear security and abstraction boundary between AI reasoning and enterprise capabilities.

---

# 🏗️ Architecture

```text
                         ┌─────────────────────┐
                         │   React / TypeScript│
                         │         UI          │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │     API Gateway     │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │      FastAPI        │
                         │    AI Platform      │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┼────────────────┐
                    │               │                │
                    ▼               ▼                ▼
                  Auth          Agent API        Document API
                    │               │                │
                    │               ▼                ▼
                    │        ┌─────────────┐        S3
                    │        │  LangGraph  │         │
                    │        │   Runtime   │         ▼
                    │        └──────┬──────┘    Processing
                    │               │
                    │       ┌───────┼────────┐
                    │       │       │        │
                    │       ▼       ▼        ▼
                    │      RAG     MCP     Workflow
                    │       │       │        │
                    │       │       ▼        │
                    │       │   MCP Server   └──────┐
                    │       │       │               │
                    │       │   ┌────────┼──────┐   │
                    │       │   ▼        ▼      ▼   │
                    │       │ Contract Policy Task  │
                    │       │   Tools  Tools Tools  │
                    │       │       │               │
                    └───────┼───────┼───────────────┘
                            │       │
                            ▼       ▼
                    ┌──────────────────────┐
                    │   Enterprise Data    │
                    │                      │
                    │ PostgreSQL / S3 /    │
                    │ Vector Store / Redis │
                    └──────────────────────┘


                     ┌─────────────────────┐
                     │    AWS Bedrock      │
                     │   Claude Models     │
                     └──────────┬──────────┘
                                │
                                ▼
                         LLM Inference


        ┌───────────────────────────────────────────────┐
        │              AI OPERATIONS                    │
        │                                               │
        │ Langfuse │ Evaluation │ OpenTelemetry         │
        │ CloudWatch │ Prompt Versioning                │
        └───────────────────────────────────────────────┘


        ┌───────────────────────────────────────────────┐
        │               PLATFORM                        │
        │                                               │
        │ Terraform │ Docker │ CI/CD │ ECS │ Lambda     │
        │ IAM │ Secrets Manager │ API Gateway           │
        └───────────────────────────────────────────────┘
```

---

# 🔑 Architectural Principles

SuitsFlow follows several principles that guide the system design.

### 1. LLMs never directly access enterprise databases

AI models interact with enterprise capabilities through controlled application interfaces and MCP tools.

### 2. LLMs never determine authorization

Authentication and authorization are enforced deterministically by the application.

```text
JWT
 ↓
Identity
 ↓
Tenant
 ↓
RBAC
 ↓
Permission
 ↓
Tool / Data Access
```

### 3. Retrieved documents are untrusted data

Documents may contain instructions intended to manipulate the model.

Therefore:

> **Retrieved content is treated as data, not authority.**

### 4. State-changing actions require authorization

The agent can propose an action, but sensitive operations can require explicit approval.

```text
Agent
 ↓
Action Proposal
 ↓
Authorization
 ↓
Human Approval
 ↓
MCP Tool
 ↓
Enterprise System
```

### 5. Prefer deterministic workflows where possible

Agents are used where reasoning is valuable.

Deterministic application logic is preferred where behavior can be explicitly defined.

### 6. Every AI execution should be observable

We track:

* model
* prompt version
* latency
* tokens
* estimated cost
* retrieval
* tool calls
* errors
* evaluation results

### 7. AI behavior must be evaluated

Traditional unit tests are insufficient for generative AI systems.

SuitsFlow includes dedicated evaluation pipelines for:

* RAG quality
* answer correctness
* citation accuracy
* tool selection
* tool arguments
* workflow completion
* security behavior
* regression detection

### 8. Infrastructure should be reproducible

AWS infrastructure is managed through Terraform rather than relying on manually configured environments.

---

# 🧩 Major Use Cases

## 1. Enterprise Legal Q&A

**Question:**

> What is our data retention policy?

```text
User
 ↓
FastAPI
 ↓
LangGraph
 ↓
RAG
 ↓
Authorized Documents
 ↓
Claude / Bedrock
 ↓
Answer + Citations
```

---

## 2. Contract Expiration Search

**Question:**

> Which contracts expire within 90 days?

The system recognizes that this is structured-data retrieval rather than a semantic knowledge question.

```text
User
 ↓
Agent
 ↓
MCP
 ↓
Contract Tool
 ↓
PostgreSQL
 ↓
Results
 ↓
LLM Summary
```

---

## 3. Contract Risk Analysis

**Question:**

> Analyze the Acme contract and identify potential legal risks.

```text
Contract
   ↓
Contract Retrieval
   ↓
Clause Extraction
   ↓
Policy Retrieval
   ↓
Risk Analysis
   ↓
Validation
   ↓
Risk Report
   ↓
Citations
```

---

## 4. Compliance Review

**Question:**

> Check this vendor contract against our company compliance policies.

```text
              Contract
                  │
          ┌───────┴────────┐
          ▼                ▼
    Contract RAG       Policy RAG
          │                │
          └───────┬────────┘
                  ▼
             Comparison
                  │
                  ▼
            Risk Findings
                  │
                  ▼
         Compliance Report
```

---

## 5. Human-in-the-Loop Legal Workflow

**Request:**

> Create a legal review task for this high-risk contract.

```text
User Request
     ↓
Agent
     ↓
Risk Analysis
     ↓
Action Proposal
     ↓
Authorization
     ↓
Human Approval
     ↓
MCP
     ↓
Create Review Task
```

The system deliberately separates **AI recommendation** from **business action execution**.

---

# 🛡️ Security Architecture

Security is treated as part of the AI architecture rather than an afterthought.

### Authentication

* OAuth / JWT
* User identity
* Tenant context

### Authorization

* RBAC
* Tenant isolation
* Resource-level permissions
* MCP tool authorization

### AWS Security

* IAM
* Secrets Manager
* Encryption
* Least-privilege access

### AI Security

* Prompt injection defense
* Untrusted document handling
* Tool authorization
* Output validation
* Sensitive-data controls

### Auditability

Important operations are recorded for investigation and compliance.

---

# 📊 AI Evaluation

SuitsFlow includes an evaluation framework designed to measure both **AI quality** and **agent behavior**.

### RAG Evaluation

```text
Retrieval Relevance
Context Precision
Context Recall
Faithfulness
Answer Correctness
Citation Accuracy
```

### Agent Evaluation

```text
Task Completion
Tool Selection Accuracy
Tool Argument Accuracy
Workflow Success Rate
Failure Recovery
Unnecessary Tool Calls
```

### Production Metrics

```text
Latency
Token Usage
Estimated Cost
Error Rate
Timeout Rate
Model Usage
```

Evaluation results can be compared across:

```text
Prompt Version
       ↓
Model Version
       ↓
Agent Version
       ↓
Evaluation Dataset
```

This allows AI changes to be treated as measurable engineering changes rather than subjective improvements.

---

# 👀 Observability

SuitsFlow uses separate observability mechanisms for traditional application behavior and LLM behavior.

### Application Observability

* OpenTelemetry
* CloudWatch
* structured logs
* distributed traces
* application metrics

### AI Observability

* Langfuse
* LLM traces
* prompt versions
* token usage
* latency
* tool calls
* retrieval context
* evaluation scores

Example trace:

```text
Request
  │
  └── LangGraph Run
        │
        ├── Intent Classification
        │
        ├── Retrieval
        │     └── Vector Store
        │
        ├── Claude
        │
        ├── MCP Tool
        │     └── PostgreSQL
        │
        └── Final Response
```

---

# ☁️ AWS Architecture

SuitsFlow is designed around an AWS-native deployment model.

| AWS Service       | Purpose                            |
| ----------------- | ---------------------------------- |
| Amazon Bedrock    | LLM inference                      |
| ECS/Fargate       | FastAPI and agent services         |
| API Gateway       | API entry point                    |
| Lambda            | Event-driven/background processing |
| S3                | Document storage                   |
| Aurora/PostgreSQL | Transactional data                 |
| Redis             | Caching and short-lived state      |
| DynamoDB          | Agent/workflow state               |
| IAM               | Access control                     |
| Secrets Manager   | Secrets                            |
| CloudWatch        | Infrastructure observability       |

Infrastructure is provisioned using:

**Terraform**

and services are packaged using:

**Docker**

---

# 🛠️ Technology Stack

### AI / GenAI

* Python
* Amazon Bedrock
* Claude
* LangChain
* LangGraph
* MCP
* RAG
* Embeddings
* LLM Evaluation

### Backend

* FastAPI
* Pydantic v2
* Async Python
* SQLAlchemy
* PostgreSQL / Aurora

### Data

* PostgreSQL
* S3
* Vector Store
* Redis
* DynamoDB

### Cloud

* AWS Bedrock
* ECS/Fargate
* Lambda
* API Gateway
* S3
* IAM
* Secrets Manager
* CloudWatch

### Infrastructure

* Terraform
* Docker
* GitHub Actions
* CI/CD

### Observability

* Langfuse
* OpenTelemetry
* CloudWatch

### Frontend

* React
* TypeScript

---

# 📁 Repository Structure

```text
suitsflow/
│
├── apps/
│   ├── api/
│   │   └── FastAPI service
│   │
│   ├── agent/
│   │   └── LangGraph agent runtime
│   │
│   ├── mcp-server/
│   │   └── Enterprise MCP tools
│   │
│   └── web/
│       └── React application
│
├── packages/
│   ├── domain/
│   ├── security/
│   ├── retrieval/
│   ├── evaluation/
│   └── observability/
│
├── infrastructure/
│   └── terraform/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── evaluation/
│   └── security/
│
├── docs/
│   ├── architecture/
│   ├── decisions/
│   ├── api/
│   └── evaluation/
│
├── scripts/
│
├── docker/
│
├── .github/
│   └── workflows/
│
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

# 🗺️ Development Roadmap

SuitsFlow is being developed incrementally to demonstrate production AI engineering practices.

### Phase 1 — Foundation

* [ ] Repository architecture
* [ ] FastAPI service
* [ ] PostgreSQL
* [ ] SQLAlchemy async layer
* [ ] Pydantic v2
* [ ] Authentication
* [ ] Contract APIs
* [ ] Docker development environment

### Phase 2 — Document Intelligence

* [ ] S3 document storage
* [ ] Document ingestion
* [ ] Text extraction
* [ ] Chunking
* [ ] Embeddings
* [ ] Vector retrieval
* [ ] Metadata filtering
* [ ] Citations

### Phase 3 — GenAI

* [ ] Amazon Bedrock
* [ ] Claude
* [ ] LangChain
* [ ] LangGraph
* [ ] Agent state
* [ ] Contract analysis workflow
* [ ] Compliance workflow

### Phase 4 — MCP

* [ ] MCP server
* [ ] Contract tools
* [ ] Policy tools
* [ ] Task tools
* [ ] Tool authorization
* [ ] Tool failure handling

### Phase 5 — Enterprise Security

* [ ] OAuth/JWT
* [ ] RBAC
* [ ] Tenant isolation
* [ ] Resource-level authorization
* [ ] Prompt injection protection
* [ ] Audit logging
* [ ] Secrets management

### Phase 6 — Production Infrastructure

* [ ] Terraform
* [ ] AWS networking
* [ ] ECS/Fargate
* [ ] API Gateway
* [ ] Lambda
* [ ] CI/CD
* [ ] Environment management

### Phase 7 — Observability

* [ ] OpenTelemetry
* [ ] CloudWatch
* [ ] Langfuse
* [ ] LLM tracing
* [ ] Cost tracking
* [ ] Latency tracking

### Phase 8 — AI Evaluation

* [ ] Golden dataset
* [ ] RAG evaluation
* [ ] Agent evaluation
* [ ] Tool evaluation
* [ ] Security evaluation
* [ ] Regression testing
* [ ] Prompt version comparison

### Phase 9 — Governance & Reliability

* [ ] Human-in-the-loop
* [ ] Workflow persistence
* [ ] Retries
* [ ] Timeouts
* [ ] Idempotency
* [ ] Failure recovery
* [ ] AI governance controls

---

# 🎯 Engineering Goals

SuitsFlow is intentionally designed to demonstrate the engineering capabilities required to build and operate modern enterprise AI systems:

```text
Software Engineering
        +
System Design
        +
Generative AI
        +
Agent Architecture
        +
RAG
        +
MCP
        +
AWS
        +
Security
        +
Observability
        +
Evaluation
        +
Infrastructure
        +
Reliability
```

The project prioritizes **engineering depth over feature count**.

---

# 📚 Architecture Documentation

Detailed architecture decisions will be documented as the system evolves.

Planned documentation includes:

* System Architecture
* Domain Model
* Data Architecture
* RAG Architecture
* Agent Architecture
* MCP Architecture
* Security Architecture
* AWS Architecture
* Evaluation Strategy
* Observability Strategy
* AI Governance
* Architecture Decision Records (ADRs)

---

# 👨‍💻 Project Status

🚧 **Active development**

SuitsFlow is being built as a hands-on exploration of production-grade enterprise AI engineering patterns.

The implementation and architecture will evolve incrementally as new capabilities are introduced and evaluated.

---

## ⭐ Key Technologies

`Python` `FastAPI` `Pydantic` `LangChain` `LangGraph` `MCP` `RAG` `Amazon Bedrock` `Claude` `AWS` `PostgreSQL` `Redis` `DynamoDB` `S3` `Terraform` `Docker` `ECS` `Lambda` `React` `TypeScript` `Langfuse` `OpenTelemetry` `CI/CD`

---

## 📌 Disclaimer

SuitsFlow is an independent engineering project created for learning, experimentation, and demonstration of enterprise AI architecture patterns. It is not affiliated with or endorsed by any Company/Organization.

---

## Local development

The first application slice is a FastAPI service with liveness and readiness endpoints. Python 3.11 is the supported local runtime.

```bash
python -m pip install uv==0.11.28
uv sync --locked --extra dev
uv run --no-sync uvicorn suitsflow.main:app --reload
```

Then visit `http://localhost:8000/api/v1/health`.

Settings have local defaults; optionally copy `.env.example` to `.env` (PowerShell:
`Copy-Item .env.example .env`). Dependencies are resolved in the committed `uv.lock`;
update it deliberately when changing dependencies. If your network uses a trusted
system certificate, use `uv --system-certs sync --locked --extra dev`.

`/api/v1/health` checks process liveness. `/api/v1/ready` executes a PostgreSQL query
and returns 503 if the database is unavailable or exceeds the configured timeout
(default three seconds). Readiness checks connectivity, not migration currency.

To run the API with local PostgreSQL:

```bash
docker compose up -d postgres
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose up -d api
```

Run the quality suite before committing:

```bash
uv run --no-sync ruff format --check src tests migrations
uv run --no-sync ruff check src tests migrations
uv run --no-sync mypy src
uv run --no-sync pytest
```

### Database migrations and integration tests

For a locally running API, start PostgreSQL and apply migrations with
`uv run --no-sync alembic upgrade head`. Migrations read `SUITSFLOW_DATABASE_URL`
from the environment or `.env`. Apply them once as a deployment step before
starting API workers; application startup does not create or modify tables.

The initial migration creates `tenants` with UUID identifiers, timezone-aware
timestamps, a nonblank name, and an `active` or `suspended` status. UUIDs are assigned
by the ORM; direct SQL inserts must supply one. SQLAlchemy updates `updated_at` on
ORM updates; direct SQL writers must set it explicitly. Tenant-scoped authorization
and additional domain tables will be implemented in subsequent slices.

Sessions are scoped to a request. Services explicitly commit successful transactions;
session cleanup rolls back uncommitted changes. A session must not be shared across
concurrent tasks. The application disposes its connection pool on shutdown.

Integration tests need an **empty, disposable database** whose name ends in `_test`.
They apply migrations, exercise constraints and transactions, verify readiness,
check model/schema drift, and downgrade/upgrade before removing the test schema.
CI supplies a dedicated PostgreSQL 16 service. To run locally in PowerShell:

```powershell
docker compose --profile test up -d --wait postgres-test
$env:SUITSFLOW_TEST_DATABASE_URL = "postgresql+asyncpg://suitsflow:suitsflow@localhost:5433/suitsflow_test"
uv run --no-sync pytest
docker compose --profile test stop postgres-test
```

Without `SUITSFLOW_TEST_DATABASE_URL`, PostgreSQL integration tests are skipped.
To add a migration, edit the models, run
`uv run --no-sync alembic revision --autogenerate -m "describe change"`, and review
the generated upgrade and downgrade before applying it. `alembic check` detects
model/schema drift. Downgrading revision `0001` deletes the tenant table and its data;
use downgrade only against disposable development databases.

### Tenant access development slice

`GET /api/v1/tenants/{tenant_id}` follows route → service → repository boundaries.
Only a `tenant_admin` can read the administrative details of their own active tenant.
Missing or invalid credentials return 401. Unknown or disabled users, inactive tenant
membership, and insufficient roles return 403. With valid membership, inaccessible
or nonexistent target tenants return the same 404 response. Tenant and role
headers do not select an identity or change access. The repository applies the
authenticated tenant scope to its query, and services enforce the role policy.

Authentication is disabled by default: protected routes return 401 until a provider
is configured. This slice supplies an **opt-in local development provider**, using
one opaque bearer token mapped to one server-configured user and tenant identity. It is not JWT or
OAuth authentication and cannot be enabled in staging or production. Verified
production identity and richer policies remain separate implementation work.
Tenant creation and membership administration APIs are not exposed yet.

For the locally running `uvicorn` process, set these values in `.env`:

```dotenv
SUITSFLOW_DEVELOPMENT_AUTH_ENABLED=true
SUITSFLOW_DEVELOPMENT_AUTH_TOKEN=<random token of at least 32 characters>
SUITSFLOW_DEVELOPMENT_USER_ID=<existing active user UUID in the selected tenant>
SUITSFLOW_DEVELOPMENT_TENANT_ID=<existing active tenant UUID>
```

Generate a token with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Keep it in the ignored `.env` file. The user must exist in `users` within the selected
tenant and have a `tenant_admin` assignment through `roles` and `user_roles` to read
tenant administration. Roles are read from PostgreSQL on every request; the former
`SUITSFLOW_DEVELOPMENT_ROLE` setting no longer grants access and should be removed.
Supply `Authorization: Bearer <token>` when calling the endpoint. The
Compose API does not inherit these opt-in settings; use the local `uvicorn` process
for this development flow. Integration tests provision their own tenants and exercise
successful reads, denied roles, cross-tenant access attempts, and suspended tenants.

Migration `0002` adds tenant-owned users, roles, and assignments. User emails must be
trimmed and lowercase, with uniqueness within a tenant. Supported roles are
`tenant_admin` and `member`; tenant administration currently requires `tenant_admin`.
Composite foreign keys prevent a user from receiving a role from another tenant,
and restrictive delete rules prevent accidental removal of referenced records.
Disabling a user, suspending a tenant, or revoking roles affects subsequent requests
without restarting the API. There are no membership mutation endpoints yet.
Apply `alembic upgrade head` before using the endpoint; existing tenant rows are
preserved, but users and role assignments must be explicitly provisioned. Downgrading
to `0001` preserves tenants and removes membership data.

### Audited tenant updates

`PATCH /api/v1/tenants/{tenant_id}` accepts `{"name": "New tenant name"}` for an
active tenant administrator in that tenant. Names are trimmed and must contain
1–255 characters; unknown fields are rejected. Tenant status and membership cannot
be changed through this endpoint.

Migration `0003` adds `audit_logs`. Each successful name change and its audit record
commit in one transaction. If audit writing fails, the name change rolls back.
Row locking serializes concurrent updates so each record captures the correct
previous and new name. Repeating the current name returns it without adding a log.
Records include tenant, actor, action, resource, timestamp, and name before/after;
bearer tokens and arbitrary request bodies are not stored.

A PostgreSQL trigger rejects audit `UPDATE`, `DELETE`, and `TRUNCATE`. Composite
foreign keys require the actor to belong to the audited tenant. This is protection
against application mistakes, not tamper-proof storage against a database owner or
superuser, who can disable triggers or drop tables. Production deployment still
needs a restricted runtime database role distinct from the migration owner.
Downgrading to `0002` removes audit history and should only be done in a disposable
development database. Audit retrieval and broader read/denial auditing remain future work.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the feature-branch and merge workflow.

### Document and version metadata

Migration `0004` adds tenant-owned `documents` and `document_versions`. Administrators
can register document records and revision metadata; members and administrators can
read records in their own tenant. Empty or unknown role sets grant no document access.
All operations also require active database-backed tenant membership.

| Endpoint | Purpose | Required role |
| --- | --- | --- |
| `POST /api/v1/documents` | Register a draft document | `tenant_admin` |
| `GET /api/v1/documents` | List this tenant's documents | `member` or `tenant_admin` |
| `GET /api/v1/documents/{id}` | Read document metadata | `member` or `tenant_admin` |
| `POST /api/v1/documents/{id}/versions` | Register revision metadata | `tenant_admin` |
| `GET /api/v1/documents/{id}/versions` | List revision metadata | `member` or `tenant_admin` |

Document registration accepts `name` (trimmed, 1–255 characters) and `document_type`
(`contract`, `policy`, or `other`). Version registration accepts `mime_type`,
`file_size` (1–104857600 bytes), and `checksum` (64 lowercase SHA-256 hex characters).
Supported media types are PDF, plain text, and DOCX. These are **caller-declared
metadata**, not verified file contents. No storage key or upload URL is accepted or
returned, and documents remain `draft`; file upload, verification, extraction, and
ready-state transitions are future slices. The version creator is recorded as
`created_by`, not as a verified uploader.

Tenant and creator IDs come from the authenticated principal. Unknown request fields
are rejected. A cross-tenant or nonexistent document returns the same 404. List
endpoints support `limit` (default 50, maximum 100) and `offset` (0–100000).
Documents sort newest first, with IDs breaking timestamp ties; versions sort by number.

Version numbers are assigned by the server while holding the document row lock.
Database uniqueness and composite foreign keys protect revision numbering and
same-tenant document/creator relationships. Metadata and its audit record commit
together; failed auditing rolls both back. Each accepted registration is a new
revision, even if its checksum matches a prior revision. Requests are not yet
idempotent, so retrying a successful registration creates another record.
There are no document deletion or version-edit endpoints. Restrictive foreign keys
preserve referenced records. Audit events record identifiers and version numbers,
not document names, contents, or hashes. Downgrading to `0003` removes document and
version metadata while retaining the earlier tenant and audit tables.
