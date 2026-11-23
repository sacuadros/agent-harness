## Change Safety & Delivery Evidence

- Before non-trivial changes, confirm the repository root, Git status, exact scope, and unrelated work to preserve.
- Before modifying global configuration, create a timestamped backup and identify the rollback path.
- Assurance comes from the classification in Slice Flow (step 2), never from the implementation route or file count. Each level requires:
  - **Basic**: one focused check and exact-diff readback.
  - **Standard**: the smallest useful regression check; broaden validation or review only when evidence warrants it.
  - **Critical**: the Critical rungs of the `verification-ladders` skill for every surface the change touches, and one fresh independent review when permitted and useful.
- Apply the smallest assurance set that covers the risk: a higher level replaces rather than stacks on lower-level checklists, and equivalent checks or reviews are never duplicated. Once the authorized scope, required checks, and applicable guardrails are satisfied, deliver the result. Add or repeat research, checks, reviews, or artifacts only for a specific unresolved evidence gap, a relevant change, or a separately authorized delivery gate.
- Evidence applies only to the exact candidate. Reuse it only while content, paths, base branch, target environment, and delivery range remain unchanged; otherwise invalidate and rerun the affected checks or review.
- After a cwd, worktree, Git, merge, test-environment, or unknown-mutation incident, inspect repository and provider state before retrying. Name a recovery command only when it can resolve the current block.
- Commits are Conventional Commits planned as work units (`work-unit-commits` skill), with no `Co-Authored-By` trailers or other AI attribution in commits or PR descriptions.
- Commit, push, or PR reuses the checks already run on that exact candidate; run only the ones it lacks.
- Report the verified outcome, exact files, checks run, every failed, skipped, or pending check, findings, unverified aspects, and local, committed, pushed, merged, and deployed states separately.
