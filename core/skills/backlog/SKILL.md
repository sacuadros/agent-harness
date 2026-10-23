---
name: backlog
description: "Turn a feature request into one-line vertical slices in .slices/<feature>.md before any code. Use automatically when work fails the Slice Flow resume test (several sessions, separate deliverables, long requirements) or the user asks for a backlog."
---

# Backlog

Produce the smallest set of vertical slices that delivers the request. No technical design yet; that waits for the `story` skill.

## Steps

1. Read the request. Ask only about real product decisions that change scope (who uses it, what each user sees, how they sign in), one question at a time, each with a suggested minimal answer. Offer expensive capabilities (offline, i18n, teams, multi-tenant, roles) as out of scope unless the user asked for them.
2. Write each slice as `As <user>, I want <one thing> so that <benefit>.`
   - One behavior per slice. Split any slice that does two things.
   - Each slice crosses every layer it needs and the user can verify it by using it.
   - No database-only, API-only, or UI-only slices. Setup belongs to the first slice that needs it.
3. Order by value and dependency. The first slice is the thinnest working path through the system.
4. Create the working file (template below) and keep it out of git:

   ```bash
   mkdir -p .slices && ex="$(git rev-parse --git-path info/exclude)" && { grep -qxF '.slices/' "$ex" || echo '.slices/' >> "$ex"; }
   ```

   In PowerShell:

   ```powershell
   New-Item -ItemType Directory -Force .slices | Out-Null; $ex = git rev-parse --git-path info/exclude; if (-not (Select-String -Path $ex -Pattern '^\.slices/$' -Quiet -ErrorAction SilentlyContinue)) { Add-Content $ex '.slices/' }
   ```

5. Show the backlog as a numbered list and wait for the user to approve, reorder, split, or drop slices. If the user said "sin pausas", show it and continue.
6. Mirror the approved file to Engram: `mem_save` with `topic_key: slices/<feature>`, `capture_prompt: false`, the full file content, and its path.
7. Load the `story` skill for B1 yourself; do not ask the user to type a command.

## Template

```markdown
# <Feature>
Branch: `<branch>` · Runner: `<test command>`

## Specs
S1. "<user requirement, verbatim, in the user's language>"
S2. (assumption) <anything inferred, marked as such>

## Backlog
- [ ] B1 (S1) As <user>, I want <one thing> so that <benefit>.
- [ ] B2 (S2) ...

## Now
(empty until the story skill runs)

## Log
L1 <date> user (verbatim): > <original request>
```

## Rules

- Never add requirements the user did not ask for; record inferences as assumptions.
- Reordering or dropping a slice is cheap: edit the file, add a Log line, update the mirror.
- When the user changes a requirement, append a dated Log entry with their words, rewrite only the affected `S#`, and reopen only the affected slices.
- Do not detail or build slices here; hand off to `story`, then `pair`.
