# SuitsFlow: Product and System Overview

## Purpose

SuitsFlow is an enterprise legal and compliance AI platform. It helps authorized users retrieve legal knowledge, inspect structured contract data, analyze contracts against policy, and propose controlled workflow actions.

The project is deliberately designed as an end-to-end agent-engineering portfolio: an LLM is a bounded reasoning component inside a secure, observable application—not the application itself.

## Primary users

| Persona | Primary capabilities |
|---|---|
| Legal counsel | Search and analyze contracts; create review requests |
| Compliance analyst | Query policies; perform compliance reviews; create reports |
| Legal reviewer | Validate findings; approve or reject proposed actions |
| Administrator | Manage identity, roles, policy configuration, and audit access |

## Core request types

| Request type | Example | Primary path |
|---|---|---|
| Knowledge | “What does the retention policy require?” | Authorized RAG → grounded response + citations |
| Structured data | “Which contracts expire in 90 days?” | Authorized MCP tool → PostgreSQL → summary |
| Workflow | “Review Acme and create a task if risk is critical.” | LangGraph workflow → validation → approval → tool |

RAG is for authorized unstructured knowledge. Tools are for structured data and actions. A request may use both.

## System context

```text
React / TypeScript UI
        │ HTTPS
        ▼
API Gateway → FastAPI application
                    │
       ┌────────────┼─────────────┐
       ▼            ▼             ▼
  Identity/RBAC  Agent runtime  Document services
                     │
           ┌─────────┼──────────┐
           ▼         ▼          ▼
          RAG       MCP      Workflows
           │         │
           ▼         ▼
  S3 / vector index / PostgreSQL / Redis
                     │
              Amazon Bedrock
```

The production target is AWS-native: Bedrock for model inference; ECS/Fargate for services; S3 for documents; Aurora PostgreSQL for transactional data; Redis for short-lived state; Lambda/queues for asynchronous work; and Terraform for reproducible infrastructure.

## Architectural principles

1. **Deterministic controls surround probabilistic reasoning.** Authorization, tenant isolation, validation, approval policy, retries, and auditing are application responsibilities.
2. **Tenant context is explicit and propagated.** No data access occurs without it.
3. **Documents are data, not instructions.** Retrieval never elevates document content to system authority.
4. **Tools are bounded capabilities.** The model may propose a tool call; deterministic code authorizes and validates it before execution.
5. **Actions are separate from recommendations.** High-impact mutations may pause for human approval.
6. **Quality is measurable.** Agent behavior, retrieval, citations, latency, and cost are evaluated and traced.

## Major capabilities

- Contract and policy ingestion with versions, chunks, metadata, and citations
- Contract expiration search and contract/policy retrieval
- Contract-risk and compliance-review workflows with structured findings
- Review-task creation through approved, authorized tools
- Audit records for material user and agent activity

## Initial implementation boundary

The first vertical slice should prove one secure workflow end to end: seed a tenant, contracts, and policies; answer a cited policy question; return expiring contracts through a tool; and create a review-task proposal that requires approval. AWS scale-out components remain target architecture until justified by the local implementation.

## Related documents

The [architecture index](README.md) defines the reading order. Application responsibilities are defined in [application architecture](06-application-architecture.md); agent-specific behavior begins in [agent architecture](07-agent-architecture.md).
