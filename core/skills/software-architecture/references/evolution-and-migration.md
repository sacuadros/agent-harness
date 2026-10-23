# Evolution and migration

Prefer reversible increments that preserve a working system.

## Migration contract

- Current, transition, and target states.
- Compatibility window and supported version combinations.
- Data/schema change sequence and ownership.
- Backfill, dual-read/write, replay, reconciliation, or cutover behavior only when actually required.
- Observability and acceptance signals for each step.
- Abort threshold and rollback procedure.
- Cleanup condition and owner.

## Fitness checks

Use the smallest executable checks that protect the decision:

- dependency direction or forbidden imports;
- public contract/schema compatibility;
- tenant or data-ownership boundaries;
- latency, error-rate, queue, or capacity threshold;
- deployability or mixed-version smoke check;
- recovery, replay, idempotency, or failover scenario;
- configuration or infrastructure policy already supported by the project.

Do not add a new architecture-testing framework when an existing test, linter, build rule, query, or script can prove the invariant.

## Stop conditions

Pause or reverse when observed error, data divergence, latency, cost, or support burden crosses the approved threshold. Do not continue a migration because the target architecture is aesthetically preferred.
