# MCP Tool Architecture

## Purpose

MCP exposes narrowly scoped enterprise capabilities to the agent. It is an integration boundary, not a security bypass.

```text
Agent proposal → MCP tool → authorization → application service → repository → data
```

## Initial tool catalog

| Domain | Read tools | State-changing tools |
|---|---|---|
| Contracts | `search_contracts`, `get_contract`, `get_contract_clauses`, `get_expiring_contracts` | none initially |
| Policies | `search_policies`, `get_policy`, `check_compliance_requirement` | none initially |
| Tasks | `get_tasks` | `create_review_task`, `assign_reviewer`, `update_review_status` |

## Tool contract rules

- Every tool has a typed input and typed response model.
- The authenticated principal and tenant context come from the server-side request context, never model arguments.
- Tools accept stable domain identifiers and pagination limits; they never accept SQL or arbitrary filters.
- A server-side authorization decision precedes service execution.
- Mutations use an idempotency key, write an audit record, and evaluate approval policy.

## Error contract

Tools return categorized failures: validation, authorization, not-found, conflict, transient, timeout, or internal. The runtime decides retry eligibility from this category, not from free-form error text.

## Initial implementation

Expose the two read paths and `create_review_task` as a proposed action requiring approval. Keep MCP in-process or local for development; preserve the boundary so it can be operated as a separate server later.
