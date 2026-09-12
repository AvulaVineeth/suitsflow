# Security Architecture

## Security model

SuitsFlow treats legal documents, user prompts, retrieved content, model responses, and tool arguments as potentially untrusted. Authorization is deterministic application logic.

```text
JWT/OAuth → principal → tenant context → RBAC/resource policy → data or tool access
```

## Controls

| Concern | Control |
|---|---|
| Tenant isolation | Tenant ID required for every protected query, index filter, and tool call |
| Identity | Verified JWT/OAuth claims; no user identity accepted from model output |
| Authorization | RBAC plus resource-level checks in services and MCP tools |
| Secrets | Environment-local development secrets; AWS Secrets Manager in deployment |
| Data protection | TLS in transit, encryption at rest, least-privilege IAM |
| Prompt injection | Delimit retrieved text as untrusted data; never grant instructions from it authority |
| Output safety | Validate schemas, evidence references, and permitted action values |
| Auditability | Append-only records for material reads, mutations, approvals, and agent activity |

## Action policy

Read-only operations may run automatically after authorization. Mutations—task assignment, status changes, and external communication—require explicit policy evaluation and, where configured, a human approval interrupt.

## Initial implementation

Implement a development identity provider, explicit tenant-scoped repository methods, role checks, audit records for mutations, and a prompt-injection test corpus before external integrations.
