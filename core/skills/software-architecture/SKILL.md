---
name: software-architecture
description: Evaluate or evolve software architecture when work changes system boundaries, service contracts, data flow, resilience, scalability, migrations, or major dependencies.
---

# Software Architecture

Make the smallest defensible architectural decision from live evidence. Architecture is a set of constraints and tradeoffs, not a diagram or a preferred pattern.

## Non-negotiables

- Resolve the real project, domain vocabulary, existing decisions, runtime topology, and current constraints before proposing a target state.
- Use CodeGraph according to repository instructions before broad structural exploration.
- Separate verified constraints, assumptions, preferences, risks, and decisions.
- Prefer the current architecture when it can meet measurable needs with a smaller change.
- Do not default to microservices, event-driven systems, new layers, generic repositories, interfaces with one implementation, or platform migrations.
- Route security-sensitive concerns to `secure-development` and external technology choices to `dependency-safety`.

## Workflow

### 1. Confirm significance

Continue only when the decision materially affects a boundary, contract, state model, data owner, deployment unit, integration, failure domain, migration, or quality attribute. Otherwise return to the normal development workflow.

### 2. Establish the current system

Inspect live code, configs, contracts, schemas, deployment evidence, domain language, ADRs, incidents, metrics, and constraints. State what is verified and what remains inferred.

### 3. Define decision drivers

Identify stakeholders and their concerns. Write only the quality scenarios that can change the decision, each with context, stimulus, expected response, and measurable threshold. Read `references/quality-attributes.md`.

### 4. Compare viable options

Include the current approach when viable. Compare 2–3 materially different options across delivery cost, operability, security, data consistency, failure isolation, performance, evolution, reversibility, and team ownership. Eliminate options that fail a hard constraint before scoring preferences.

### 5. Describe only useful views

Read `references/views-and-diagrams.md`. Produce the smallest set of views needed by the affected stakeholders. Every box and arrow must have a named responsibility, ownership, protocol, or dependency; omit decorative architecture diagrams.

### 6. Decide and record

Recommend one option and explain why the others lost. Read `references/decisions-and-adrs.md`. Create or update an ADR only for a durable, architecturally significant decision whose rationale future maintainers would otherwise re-litigate.

### 7. Plan safe evolution

Read `references/evolution-and-migration.md` for migrations, replacements, data movement, compatibility, or risky rollouts. Define rollback, observability, operational ownership, and the smallest executable fitness checks that detect drift.

### 8. Hand off implementation

Architecture output informs, but does not replace, Slice Flow in `AGENTS.md`: record decisions that shape the next slice in its `## Now`, not in a separate design document. When implementation is authorized, continue in Slice Flow with its assurance level and existing quality guardrails. Apply relevant Superpowers skills within it; do not introduce another planning authority or repeat equivalent implementation and verification steps.

## Result contract

```text
Architecture decision
- Scope and stakeholders:
- Verified current state:
- Constraints and assumptions:
- Quality scenarios:
- Options and tradeoffs:
- Recommended decision:
- Views produced:
- Migration and rollback:
- Fitness checks and operational owner:
- ADR status:
- Residual risks and unverified items:
```

Do not claim an architecture is scalable, resilient, maintainable, or secure without a scenario, threshold, and evidence.
