It is an OpenSpec change. If the repository's `openspec/` folder, its `openspec-*` skills, or the `openspec` CLI are missing, stop and show the user the command (`openspec init --tools <agents>`, or `openspec update` after a CLI upgrade); never run those two yourself.
   - **Propose.** Resume an active change (`openspec list --json`) or load the `openspec-propose` skill. Then `openspec validate <name> --strict` must pass.
   - **Checkpoint.** Large work has one checkpoint before building: proposal approval.
   - **Apply.** Load the `openspec-apply-change` skill and build each task with the `pair` skill; a task group is a slice.
   - **Archive.** Once the suite and that validation pass, load the `openspec-archive-change` skill before the commit proposal. Stop on an unchecked task.
   - These instructions win over an OpenSpec skill on pace, questions, approvals, delegation, and commits. Medium work that changes a requirement in `openspec/specs/` is a change too.
