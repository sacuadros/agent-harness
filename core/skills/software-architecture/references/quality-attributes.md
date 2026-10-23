# Quality attributes

Use [ISO/IEC 25010:2023](https://www.iso.org/standard/78176.html) as vocabulary, not as a checklist. Select only qualities that can change the decision.

## Scenario format

```text
Quality:
Stakeholder:
Context:
Stimulus:
Expected response:
Measure or threshold:
Evidence source:
```

Prefer observable scenarios over adjectives:

- Performance: p95 latency, throughput, queue delay, payload size, rendering or batch deadline.
- Reliability: tolerated failure, recovery time, recovery point, retry/replay behavior, partial-operation semantics.
- Security: protected asset, attacker capability, trust boundary, authorization or containment invariant.
- Maintainability: change scenario, affected modules, lead time, test surface, deployment independence.
- Compatibility: supported clients, version window, schema evolution, downgrade or mixed-version behavior.
- Operability: alert, diagnosis, owner, runbook, safe intervention, audit evidence.
- Cost: workload assumption, unit cost, capacity ceiling, budget guardrail.
- Accessibility and quality in use: affected task, user group, environment, completion or error measure.

Do not invent SLOs. If no baseline or owner exists, mark the threshold as a proposed decision requiring confirmation.
