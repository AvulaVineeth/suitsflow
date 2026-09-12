# Agent Architecture

## Purpose and boundary

The agent runtime orchestrates reasoning workflows. It does not authenticate users, determine permissions, issue raw database queries, or bypass application services. Those remain deterministic boundaries.

```text
FastAPI → AgentService → LangGraph runtime → RAG and authorized MCP tools
```

## Execution state

Each run has an explicit, durable state:

```text
request, principal, tenant_id, conversation_id
intent, plan, retrieved_context, tool_calls, tool_results
findings, citations, approval, final_answer
errors, retry_count, trace metadata
```

`tenant_id` and the authenticated principal are supplied by the application, never inferred by the model. Model-produced values are validated before they enter state used by deterministic code.

## Graph

```text
START → understand → classify
                       ├─ knowledge → retrieve ─┐
                       ├─ data ─────→ tool ─────┤
                       └─ workflow ─→ plan ─────┤
                                                ▼
                                           analyze → validate
                                                          │
                                           approval required?
                                              ├─ yes → interrupt/resume
                                              └─ no
                                                          ▼
                                                       respond → END
```

## Node responsibilities

| Node | Responsibility | Deterministic guard |
|---|---|---|
| Understand | Convert language to a typed intent | Pydantic schema and allowed intents |
| Classify | Select knowledge, data, or workflow path | Route only to registered paths |
| Retrieve | Request relevant authorized context | Tenant and ACL filters precede retrieval |
| Tool | Propose a bounded capability call | Tool allowlist, RBAC, argument validation |
| Analyze | Produce structured risks or synthesis | Schema, evidence, and domain validation |
| Validate | Check cited resources and business rules | Resource ownership and value constraints |
| Approval | Pause material actions | Approval policy and authenticated reviewer |
| Respond | Present validated result | Citation and output filtering |

## Structured findings

Risk analysis produces a typed result rather than parsed prose: `category`, `severity`, `description`, `evidence`, `confidence`, and referenced clause/policy identifiers. Valid severities are `low`, `medium`, `high`, and `critical`. A confidence field is model-reported metadata, not a quality guarantee.

## Failure policy

- Retry bounded transient model or network failures (initially two attempts).
- Do not retry authorization, validation, or not-found errors.
- Persist enough state to resume an approval or safely report a failed workflow.
- Record the category and final outcome of every failure.

## Initial implementation

Implement three typed paths: policy Q&A, contract-expiration lookup, and contract-risk review. Use a single graph with deterministic routing before adding planning loops or multiple agents.
