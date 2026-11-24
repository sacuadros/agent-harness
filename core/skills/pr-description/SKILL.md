---
name: pr-description
description: "Write a pull request description a reviewer can check quickly: what changed and why, before/after evidence, a diagram when the change crosses surfaces, and whether a person needs to review it. Use when the user asks to open, prepare, or describe a PR."
---

# PR Description

Write the description; do not open the pull request. Opening one needs the user's approval for the destination and the operation.

Use only evidence from the exact candidate: the final diff and the checks already run on it. Rerun nothing they cover.

## Sections, in this order

1. **What and why.** Two sentences: the behavior that changed and the request or problem behind it. Link the issue when there is one.
2. **Before and after.** Pick the form that matches the change:
   - A UI change: the same screen before and after, as screenshots, or a short recording when the change is an interaction.
   - A behavior change with no UI: the same command or request before and after, with its output.
   - No observable change (a refactor): say so, and name the test that pins the behavior.
3. **Diagram.** Only when the change crosses two or more surfaces or changes a flow: one Mermaid diagram of the flow after the change. Skip it otherwise.
4. **Human review.** One line, taken from the class and Risk line of the work:
   - `Human review: required (<risk item>)` when the work is Critical. Name the files where the risk lives.
   - `Human review: optional` otherwise, followed by the checks that passed.
5. **Checks.** Each command and its result. List every skipped or failed check with the reason.

## Rules

- Never invent evidence. When a screenshot or a "before" cannot be captured, say what is missing and why.
- Capture the "before" from the base branch, not from memory.
- No AI attribution in the description.
- Keep it short. A reviewer should reach the Human review line without scrolling past a wall of text.
