---
name: story
description: "Refine the next backlog slice just before building it: acceptance criteria, ordered test list, out of scope. Use automatically after the backlog is approved or a slice closes, or when the user asks to detail a story or ticket."
---

# Story

Detail one slice, the next unchecked one in `.slices/<feature>.md` unless the user names another. Never detail later slices.

## Steps

1. Read the slice and its `S#`. Read only the code needed to know the current behavior (CodeGraph first in indexed repos).
2. List the ambiguities. For each, propose the answer you would assume. Ask the user only about answers that change behavior, and let them confirm the rest in one pass.
3. Write `## Now` in the working file:

   ```markdown
   ## Now: B2 (S2)
   ### Acceptance criteria
   - AC1 (S2) Given <state>, when <action>, then <observable result>.
   ### Tests (in order)
   1. <simplest observable case, at the level the user would check: endpoint, UI, or CLI>
   2. <next case>
   ### Decisions
   - <only choices the user must make or confirm; no file-by-file plan>
   ### Out of scope
   - <what this slice will not do>
   ### Suggestions
   - <optional follow-ups, not part of this slice>
   ```

4. Show `## Now` and wait for approval; if the user said "sin pausas", show it and continue. Add a Log line with the decisions, then update the Engram mirror (`topic_key: slices/<feature>`).
5. Load the `pair` skill yourself and start the first test.

## Rules

- Acceptance criteria describe behavior, not implementation. Leave patterns, layers, and file layout to the `pair` skill.
- Every criterion links an `S#`; every test maps to a criterion.
- Keep the slice small enough to build and review in one sitting. If the test list grows past about eight cases, propose splitting the slice in the backlog instead.
