## Proportional Test-Driven Development

- Follow the repository testing policy and reuse its existing test stack.
- Start with a failing test or executable check for reproducible defects, critical contracts, security or data-safety behavior, and requirements with a precise observable outcome.
- For other non-trivial logic, leave the smallest focused regression check that would fail if the behavior breaks; test-first is optional when exploration is required.
- Write one failing test per requested rule and one regression test per touched existing behavior, then stop. Do not prove one behavior twice at different levels; pick cases by equivalence classes and boundaries. Critical assurance may add cases for its named risk.
- Do not force TDD for documentation, configuration-only changes, mechanical refactors, generated code, or behavior that cannot be tested reliably. State the reason and any unverified risk.
- When claiming TDD, preserve the Red → Green → Refactor sequence and rerun the focused check after the final diff.
