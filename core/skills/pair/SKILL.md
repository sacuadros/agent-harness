---
name: pair
description: "Build the current slice test by test with TDD. Use automatically once the story is written, when the user says \"pair\", or to implement the ## Now section of .slices/<feature>.md."
---

# Pair

You drive and keep going; the user steps in only when needed. Work from `## Now` in `.slices/<feature>.md`, or from the user's request for small work.

## Loop, one test at a time

1. **RED.** Write only the next test from the list. Run it and show that it fails for the expected reason. Stage it with `git add <test file>`.
2. **GREEN.** Write the minimum code that passes it. Run the focused test, then the suite once. If `git diff -- <test files>` shows the staged test changed, stop and explain why.
3. **REFACTOR.** Only for a stated reason: duplication that exists now, a structure the user asked for, or a need the next known slice requires. Tests stay untouched and green.
4. **Show.** Summarize the change in one or two lines and point to the diff.
5. **Work unit.** Test and code form one work unit. Do not commit; the commit proposal comes when the backlog is done or the user stops.

Continue through the test list without waiting. When the user says "pair", stop after step 4 of every test.

## Alarms: stop and report

- **Loop:** the same failure twice after a fix attempt.
- **Scope creep:** code, fields, endpoints, abstractions, or files that `## Now` does not need. Remove them or ask.
- **Test cheating:** editing, skipping, deleting, or weakening a test, or special-casing test input, to get green.

## Close the slice

1. Check every acceptance criterion against observed evidence: test output, or a command or URL the user can use to try it.
2. In the working file, check the slice in `## Backlog`, clear `## Now`, and add a Log line with the evidence. Update the Engram mirror.
3. Load the `story` skill yourself for the next unchecked slice. Stop here instead only when the user said "con pausas"; then report the slice and offer to continue.
4. After the last slice, report every slice's outcome and each failed, skipped, or pending check, with `Risk: none` or `Risk: <item> (reason)`. Then propose the commits, one per slice when their files do not overlap, and ask once with options: commit, commit and push, or not yet.
5. When the feature closes, delete `.slices/<feature>.md` and save a final Engram note marking it closed.
