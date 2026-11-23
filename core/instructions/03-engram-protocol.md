## Engram Persistent Memory

Engram persistent memory is active. The Engram server and the SessionStart hook deliver the full protocol.

- Only when non-trivial work closes, `mem_save` its verified durable conclusions (decisions, bugfixes, discoveries, conventions, config changes), grouped by topic.
- On any reference to past work: `mem_context` → `mem_search` → `mem_get_observation`.
- Saving to memory never replaces the answer: end every turn with the complete user-facing answer as the final message, and deliver it even when a memory call fails.
- On `ambiguous_project`, never guess: ask the user to choose one value from `available_projects`. For `mem_session_start`, retry with the repository root as `directory`.
