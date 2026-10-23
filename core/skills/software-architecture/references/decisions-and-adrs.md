# Decisions and ADRs

An ADR captures one architecturally significant decision and its rationale. Use the practices and templates catalogued by [adr.github.io](https://adr.github.io/).

## Record when

- the choice changes a durable boundary, public contract, data owner, deployment model, or technology commitment;
- alternatives were plausible and tradeoffs matter;
- reversal is costly or future teams are likely to reopen the question;
- compliance, security, reliability, or operational ownership depends on the decision.

Do not create an ADR for naming, local refactors, routine library use, temporary experiments, or a decision already governed by a current ADR.

## Minimal format

```md
# ADR-NNNN: Decision title

Status: proposed | accepted | superseded
Date:
Owners:

## Context and decision drivers

## Options considered

## Decision

## Consequences
- Positive:
- Negative:
- Risks and mitigations:

## Validation and review trigger
```

State why each rejected option lost. A decision without consequences or a review trigger is incomplete.
