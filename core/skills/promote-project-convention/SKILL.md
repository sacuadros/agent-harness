---
name: promote-project-convention
description: Use only when the user explicitly asks to turn a correction, decision, or recurring project convention into version-controlled repository documentation.
---

# Promote Project Convention

Promote one stable, verified project convention from the conversation into documentation that the repository can review and share.

## Boundaries

- Do not run automatically at session end or after ordinary feedback.
- Document project conventions, not personal preferences, temporary task state, implementation plans, `.slices/` backlogs, or secrets.
- Preserve the repository's existing documentation structure and tone. Do not add branded footers, promotional copy, analytics, or generated-conversation transcripts.
- Update an existing matching document instead of creating a duplicate.
- Do not commit, push, publish, or modify external trackers without separate authorization.

## Workflow

1. Resolve the repository root and inspect Git status. Preserve unrelated work.
2. Extract the proposed convention, its reason, known exceptions, and the correction or decision that established it.
3. Verify the convention against relevant code, tests, existing docs, and the nearest `AGENTS.md`. If evidence contradicts it, report the conflict instead of documenting it as current practice.
4. If the repository has a documentation convention, follow it. Otherwise create one concise file under `docs/conventions/<area>/<semantic-name>.md` with:
   - the convention;
   - why it matters;
   - a good example;
   - a bad example;
   - exceptions;
   - references to real repository paths.
5. Maintain a compact `## Documentation map` in the nearest applicable `AGENTS.md`. Group links by area and point to directories when listing every file would make the index noisy. Do not duplicate the document's content in `AGENTS.md`.
6. Validate referenced paths and links, inspect the exact diff, and report files changed plus anything not verified.

Ask one concise question only when the convention or target scope remains materially ambiguous after repository inspection. Otherwise proceed directly.
