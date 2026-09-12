# Application Architecture

## Scope

This document defines application-layer responsibilities and dependency direction. Agent behavior, retrieval, tool contracts, and cross-cutting controls are specified in [agent architecture](07-agent-architecture.md), [RAG architecture](08-rag-architecture.md), [MCP tool architecture](09-mcp-tool-architecture.md), and [security architecture](10-security-architecture.md).

The central question is: **when a request enters SuitsFlow, which layer is responsible for what?** The application must not become:

```text
FastAPI endpoint
    ↓
LLM
    ↓
random database queries
    ↓
random MCP calls
```

Instead, we'll build a layered architecture.

## 1. Application Architecture

The first version looks like this:

```text id="6q3j2a"
                    React / TypeScript
                           │
                           │ HTTPS
                           ▼
                    API Gateway
                           │
                           ▼
                    ┌────────────┐
                    │  FastAPI   │
                    │    API     │
                    └─────┬──────┘
                          │
              ┌───────────┼───────────┐
              │           │           │
              ▼           ▼           ▼
          Routers      Dependencies   Schemas
              │           │
              └─────┬─────┘
                    ▼
               Service Layer
                    │
        ┌───────────┼────────────┐
        │           │            │
        ▼           ▼            ▼
    Domain       Agent        Document
    Services     Runtime      Services
        │           │            │
        │           ├──────┬─────┤
        │           │      │
        │           ▼      ▼
        │          RAG     MCP
        │
        ▼
   Repository Layer
        │
        ▼
    Data Layer
        │
   ┌────┼────┬────────┐
   ▼    ▼    ▼        ▼
  PG   S3  Vector   Redis
```

This is the architecture we'll refine.

---

# 2. Why layers?

Imagine this API:

```http
POST /contracts/{contract_id}/review
```

We don't want the route handler to contain:

```python
# bad architecture

@router.post(...)
async def review_contract(...):
    contract = await db.execute(...)
    chunks = await vector_db.search(...)
    response = await bedrock(...)
    ...
```

Now the API layer knows about:

* PostgreSQL
* vector search
* Bedrock
* prompts
* authorization
* business rules

That's too much responsibility.

Instead:

```text id="x1r4x4"
HTTP Request
     ↓
Router
     ↓
Service
     ↓
Agent
     ↓
Repositories / MCP
     ↓
Infrastructure
```

Each layer has a reason to exist.

---

# 3. API / Router layer

FastAPI routers should primarily deal with **HTTP concerns**.

For example:

```text id="8f3qyp"
POST /documents
GET  /documents/{id}

GET  /contracts
GET  /contracts/{id}
POST /contracts/{id}/review

POST /agents/run

GET  /tasks
POST /tasks
```

The router handles:

* request parsing
* Pydantic validation
* dependency injection
* authentication context
* calling the appropriate service
* HTTP response

Conceptually:

```python
@router.post("/contracts/{contract_id}/review")
async def review_contract(
    contract_id: UUID,
    current_user: CurrentUser,
    service: ContractReviewService,
):
    return await service.review(contract_id, current_user)
```

Notice what isn't here:

```text
❌ SQL
❌ Bedrock calls
❌ LangGraph construction
❌ prompt logic
❌ vector search
❌ MCP implementation
```

---

# 4. Dependency layer

FastAPI's dependency injection becomes very useful here.

We previously discussed:

```text id="7v9vna"
get_current_user()
        ↓
get_db()
```

Now our architecture can extend that idea.

For example:

```text id="iy9n0v"
Request
  │
  ├── get_db()
  │
  ├── get_current_user()
  │
  ├── get_tenant_context()
  │
  └── get_authorization_context()
```

The router doesn't need to manually reconstruct these things.

This gives us:

```text id="h4g4zn"
Authentication
     ↓
Identity
     ↓
Tenant Context
     ↓
Authorization
     ↓
Service
```

---

# 5. Service layer

This is where **business/application logic** lives.

Examples:

```text id="x0m5es"
DocumentService
ContractService
ReviewService
TaskService
AgentService
ApprovalService
```

Suppose we have:

```text id="v1dr2k"
ContractReviewService
```

It might coordinate:

```text id="m3a2zo"
ContractReviewService
       │
       ├── Authorization
       │
       ├── ContractRepository
       │
       ├── AgentRuntime
       │
       └── ReviewRepository
```

The service understands the business workflow.

For example:

```text id="h1r6pd"
1. Verify user can review contract
2. Load contract
3. Start AI review
4. Receive findings
5. Persist review
6. Determine whether approval is needed
7. Return result
```

---

# 6. Repository layer

Repositories isolate database access.

For example:

```text id="j7a5n4"
ContractRepository
    ↓
PostgreSQL
```

Instead of:

```python
result = await session.execute(
    select(Contract).where(...)
)
```

being scattered throughout the application, we can have:

```python
contract = await contract_repository.get_by_id(...)
```

The service doesn't need to know the exact SQL.

This creates:

```text id="u7a2fa"
Service
   ↓
Repository interface
   ↓
SQLAlchemy implementation
   ↓
PostgreSQL
```

This is particularly useful for testing.

---

# 7. Repository vs Service

This distinction is important for interviews.

### Repository

Answers:

> **How do I access the data?**

Example:

```text id="r5q3f6"
get_contract()
find_expiring_contracts()
save_review()
get_policy()
```

### Service

Answers:

> **What should the application do?**

Example:

```text id="7u5j4x"
review_contract()
create_review()
approve_action()
assign_task()
```

So:

```text id="3i7w9x"
Service
  ↓
Repository
  ↓
Database
```

---

# 8. Agent Runtime

Now we reach the AI-specific layer.

The application should not directly scatter LLM calls throughout services.

Instead:

```text id="u2z5gq"
AgentService
     ↓
Agent Runtime
     ↓
LangGraph
```

The Agent Runtime owns things such as:

* workflow execution
* state
* model invocation
* tool selection
* retrieval
* validation
* retries
* human approval
* final response generation

Conceptually:

```text id="4h9b1d"
AgentService
     │
     ▼
LangGraph Runtime
     │
     ├── Understand
     ├── Classify
     ├── Retrieve
     ├── Tool Call
     ├── Analyze
     ├── Validate
     └── Respond
```

---

# 9. Why LangGraph belongs here

LangGraph is an **orchestration mechanism**, not our entire application architecture.

We shouldn't make this:

```text id="3s5n0j"
Everything
   ↓
LangGraph
```

Instead:

```text id="r6j5a0"
FastAPI
   ↓
Application Service
   ↓
Agent Runtime
   ↓
LangGraph
```

That keeps our domain logic independent from the agent framework where practical.

This is important because the system should still be understandable if we eventually replace LangGraph.

---

# 10. RAG boundary

Our agent runtime can invoke the RAG subsystem.

```text id="9gjh4a"
LangGraph
   ↓
RAG Service
   ↓
Retrieval
   ↓
Vector Store
   ↓
Document metadata
   ↓
Authorization filtering
```

The RAG service is responsible for things such as:

```text id="5t7r6j"
query transformation
retrieval
metadata filtering
reranking
context assembly
citations
```

The LLM should receive only the context it is authorized to use.

---

# 11. MCP boundary

MCP should also be a separate architectural boundary.

```text id="0s5q0q"
Agent Runtime
      │
      │ MCP
      ▼
Legal MCP Server
      │
      ├── Contract Tools
      ├── Policy Tools
      └── Task Tools
             │
             ▼
        Authorization
             │
             ▼
        Business Service
             │
             ▼
        Repository
```

This is an important distinction.

The agent doesn't directly do:

```text id="7v9e7u"
Agent → SQL
```

Instead:

```text id="j5g5ac"
Agent
 ↓
MCP tool
 ↓
Authorization
 ↓
Service
 ↓
Repository
 ↓
Database
```

That gives us a controlled tool boundary.

---

# 12. Example: contract expiration query

Suppose the user asks:

> "Which contracts expire in the next 90 days?"

The request travels through the architecture:

```text id="n4c2yx"
React
  ↓
API Gateway
  ↓
FastAPI
  ↓
AgentService
  ↓
LangGraph
  ↓
Intent = structured_data
  ↓
MCP
  ↓
get_expiring_contracts(days=90)
  ↓
Authorization
  ↓
ContractService
  ↓
ContractRepository
  ↓
PostgreSQL
```

The database performs:

```sql
WHERE tenant_id = ?
AND expiration_date BETWEEN ? AND ?
```

The LLM then turns the structured result into a useful response.

This is much better than asking an LLM to search a pile of PDFs for dates.

---

# 13. Example: legal knowledge question

Now:

> "What does our data retention policy say?"

Different path:

```text id="4m5m5v"
React
  ↓
FastAPI
  ↓
AgentService
  ↓
LangGraph
  ↓
Intent = knowledge
  ↓
RAG Service
  ↓
ACL filtering
  ↓
Vector Search
  ↓
Reranking
  ↓
Context
  ↓
Claude / Bedrock
  ↓
Answer + Citations
```

No MCP tool is necessary.

---

# 14. Example: complex workflow

Now:

> "Review Acme's contract for compliance risks and create a legal review task if a critical risk is found."

This is where agentic orchestration becomes valuable:

```text id="1y6c0c"
Request
  ↓
LangGraph
  ↓
Load Contract
  ↓
Retrieve Relevant Clauses
  ↓
Analyze Compliance
  ↓
Identify Risks
  ↓
Validate Findings
  ↓
Critical risk?
  │
  ├── No → Return findings
  │
  └── Yes
       ↓
    Create Action Proposal
       ↓
    Approval Required?
       │
       ├── Yes → Human Approval
       │              ↓
       │          MCP Tool
       │              ↓
       │          Create Task
       │
       └── No → MCP Tool
                    ↓
                 Create Task
```

This is a genuine reason to use LangGraph.

---

# 15. Application boundaries

At this point, our architecture has five major application boundaries:

```text id="j48t3n"
┌──────────────────────────────────────────┐
│                 FastAPI                  │
│                                          │
│  API / Auth / Request Validation         │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│            Application Services          │
│                                          │
│ Contract / Review / Task / Document      │
└──────────────────┬───────────────────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
┌─────────────────┐  ┌────────────────────┐
│  Agent Runtime  │  │   Domain Services  │
│   LangGraph     │  │                    │
│                 │  │                    │
│ RAG / Workflow  │  │ Business Rules     │
└────────┬────────┘  └─────────┬──────────┘
         │                     │
         ▼                     ▼
    ┌─────────┐          ┌─────────────┐
    │   MCP   │          │ Repositories│
    └────┬────┘          └──────┬──────┘
         │                      │
         └──────────┬───────────┘
                    ▼
             Infrastructure
```

---

# 16. Suggested repository structure

Now our actual codebase can eventually reflect this architecture:

```text id="7e8c6q"
backend/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   ├── documents.py
│   │   │   ├── contracts.py
│   │   │   ├── reviews.py
│   │   │   ├── tasks.py
│   │   │   └── agents.py
│   │   │
│   │   └── dependencies.py
│   │
│   ├── schemas/
│   │   ├── contracts.py
│   │   ├── documents.py
│   │   ├── reviews.py
│   │   └── agents.py
│   │
│   ├── services/
│   │   ├── contract_service.py
│   │   ├── document_service.py
│   │   ├── review_service.py
│   │   └── task_service.py
│   │
│   ├── agents/
│   │   ├── runtime.py
│   │   ├── state.py
│   │   ├── graph.py
│   │   ├── nodes/
│   │   └── tools/
│   │
│   ├── rag/
│   │   ├── retrieval.py
│   │   ├── reranking.py
│   │   └── citations.py
│   │
│   ├── repositories/
│   │   ├── contracts.py
│   │   ├── documents.py
│   │   ├── reviews.py
│   │   └── tasks.py
│   │
│   ├── models/
│   │   ├── tenant.py
│   │   ├── user.py
│   │   ├── contract.py
│   │   ├── document.py
│   │   └── agent_run.py
│   │
│   ├── db/
│   │   ├── session.py
│   │   └── migrations/
│   │
│   └── core/
│       ├── config.py
│       ├── security.py
│       └── logging.py
│
└── mcp/
    ├── server.py
    ├── tools/
    └── authorization.py
```

We don't need to implement all of this now. This is the **target architecture**.

---

# 17. One rule we should enforce

There should be a clear dependency direction:

```text id="2w9t0g"
API
 ↓
Services
 ↓
Repositories
 ↓
Infrastructure
```

And AI:

```text id="4t1y5w"
API
 ↓
Agent Service
 ↓
Agent Runtime
 ↓
RAG / MCP
 ↓
Services / Repositories
```

We should avoid:

```text id="4ef8r5"
Repository → Agent ❌

Database Model → LangGraph ❌

Pydantic Schema → PostgreSQL session ❌

LLM → Database directly ❌
```

This prevents tight coupling.

---

# 18. Where our architecture stands

We've now established:

```text id="x6c0n7"
                    SuitsFlow
                       │
                       ▼
              Application Architecture
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
        FastAPI      Services      Agents
          │            │            │
          │            │        LangGraph
          │            │        /       \
          │            │      RAG       MCP
          │            │       │         │
          └────────────┼───────┴─────────┘
                       ▼
                  Repositories
                       │
                       ▼
               Data Architecture
                       │
          ┌────────────┼─────────────┐
          ▼            ▼             ▼
         PG           S3        Vector/Redis
```

### Documentation status

We should now have:

```text
docs/
├── architecture/
│   ├── high-level-design.md       ✅
│   ├── data-architecture.md       🔄
│   └── application-architecture.md 🔄
│
├── decisions/
├── api/
└── evaluation/
```

I would consider both architecture documents **drafts at this point**, because we'll refine them as we make later decisions.

---

## Implementation handoff

Implement the API, dependency, service, repository, and infrastructure boundaries before binding a workflow framework to domain logic. See [agent architecture](07-agent-architecture.md), [RAG architecture](08-rag-architecture.md), and [MCP tool architecture](09-mcp-tool-architecture.md) for the interfaces that cross these boundaries.
