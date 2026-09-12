# Observability and Evaluation

## Observability

Every request carries a correlation ID. OpenTelemetry and structured application logs capture API, database, worker, and external-call behavior. Langfuse captures model inputs/outputs under the platform's data-handling policy, prompt version, token use, retrieval, tool calls, latency, and estimated cost.

```text
Request → application trace → agent run
                         ├─ retrieval span
                         ├─ model span
                         ├─ tool span
                         └─ approval / final response
```

## Evaluation suite

| Area | Measures |
|---|---|
| Retrieval | relevance, context precision/recall, authorized-source selection |
| Answers | faithfulness, correctness, citation accuracy |
| Agent behavior | task completion, tool selection, argument correctness, unnecessary calls |
| Security | tenant leakage, prompt injection, unauthorized tool attempts |
| Operations | latency, errors, tokens, cost, timeout and retry rates |

Golden cases specify an input, expected behavior, eligible sources/tools, and assertions. Results are compared across prompt, model, agent, and retrieval versions; regression thresholds block promotion.

## Initial implementation

Start with deterministic unit/integration tests plus a small versioned golden dataset for the three initial flows. Add Langfuse and OpenTelemetry before optimizing prompts or adding models.
