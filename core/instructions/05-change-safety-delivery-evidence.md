## Change Safety & Delivery Evidence

- Before non-trivial changes, confirm the repository root, Git status, exact scope, and unrelated work to preserve.
- Before modifying global configuration, create a timestamped backup and identify the rollback path.
- Select assurance independently from the implementation route and file count:
  - **Basic**: bounded, reversible work; use one focused check and exact-diff readback.
  - **Standard**: non-trivial behavior or integration; add the smallest useful regression check and broaden validation or review only when evidence warrants it.
  - **Critical**: authentication, authorization, payments, migrations, data safety, security, or public contracts; run the applicable critical checks and use one fresh independent review when permitted and useful.
- Apply the smallest assurance set that covers the risk. A higher level replaces rather than stacks on lower-level process checklists; never duplicate equivalent checks or reviews.
- Once the authorized scope, assurance-required checks, and applicable quality guardrails are satisfied, deliver the result. Add or repeat research, checks, reviews, or artifacts only for a specific unresolved evidence gap, a relevant change, or a separately authorized delivery gate.
- Evidence applies only to the exact candidate. Reuse it only while content, paths, base branch, target environment, and delivery range remain unchanged; otherwise invalidate and rerun the affected checks or review.
- After a cwd, worktree, Git, merge, test-environment, or unknown-mutation incident, inspect repository and provider state before retrying. Name a recovery command only when it can resolve the current block.
- Use Conventional Commits and plan commits as work units (see the `work-unit-commits` skill). Never add `Co-Authored-By` trailers or any AI attribution to commits or PR descriptions.
- Before commit, push, or PR, revalidate the intended candidate and focused checks. Commit, push, PR, merge, publish, and deploy remain separately authorized.
- Report exact files, checks, findings, unverified aspects, and local, committed, pushed, merged, and deployed states separately.
