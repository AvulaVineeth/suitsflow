# Reliability and Governance

## Reliability principles

- Bound timeouts, retries, and tool-call counts for every run.
- Retry only idempotent, transient operations; never retry an authorization or validation failure.
- Use idempotency keys for mutations and persist workflow progress needed to resume approvals.
- Fail safely: return a clear partial/failure result rather than fabricating an answer or repeating actions.

## Governance lifecycle

```text
Agent recommendation → deterministic validation → policy decision
                     → approval (if required) → authorized execution → audit trail
```

Agent recommendations are distinct from business actions. Approvals record requester, approver, payload summary, decision, and timestamps. Audit entries should be append-only and must not be cascade-deleted with ordinary business records.

## Operational targets

Initial targets are directional and must be verified through tests: simple non-LLM APIs under 500 ms; typical RAG or tool responses under 8 seconds; bounded agent execution within 60 seconds. Document ingestion is asynchronous.

## Initial implementation

Define typed error categories, request correlation IDs, retry policy, idempotent task creation, and an approval state machine before adding autonomous task mutation.
