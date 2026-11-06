## Quality Guardrails

- Preserve the current activation of Ponytail, Unslop, Impeccable's anti-slop checks, and other protections against slop and overengineering. Do not weaken or bypass them to save tokens, reduce latency, or simplify the workflow.
- Route selection changes orchestration, not quality requirements. Apply these protections in every Slice Flow step, inline or delegated, without introducing a competing planning authority.
- Do only what was asked. Every changed line must trace to the request or to something it strictly requires.
- Do not add features, options, refactors, docs, or cleanups beyond the request. A bug fix does not need surrounding code cleaned up.
- No helpers or abstractions for one-time use, and no design for hypothetical needs.
- No handling for scenarios that cannot happen. Keep validation at trust boundaries.
- Before any fix, check whether it adds a state, command, flag, gate, or second copy of existing truth. If it does, redesign it; the right fix often deletes or relaxes something.
- Do not guess what the user wants. Settle what you can from the code, docs, and conversation; when a requirement, scope, or product decision stays open, ask instead of assuming. Implementation choices within the request stay yours.
- When sources disagree, tests state the intent and code shows the behavior; docs count only where code or a test confirms them. Untested behavior that could be intent or accident stays open.
- Propose improvements instead of applying them. When you notice something worth doing outside the request, mention it in one line and leave it undone unless the user says to apply it.
- Consolidate only demonstrated duplicates with equivalent scope, checks, and enforcement. Similar names or goals do not prove redundancy. Investigate false positives without silently disabling the control.
