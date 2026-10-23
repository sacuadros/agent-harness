---
name: pair
description: "Build the current slice test by test with TDD while the user navigates. Use automatically after a story is approved, when the user says \"pair\", or to implement the ## Now section of .slices/<feature>.md."
---

# Pair

You drive and the user navigates. Work from `## Now` in `.slices/<feature>.md`, or from the user's request for small work.

## Loop, one test at a time

1. **RED.** Write only the next test from the list. Run it and show that it fails for the expected reason. Stage it with `git add <test file>`.
2. **GREEN.** Write the minimum code that passes it. Run the focused test, then the suite once. If `git diff -- <test files>` shows the staged test changed, stop and explain why.
3. **REFACTOR.** Only for a stated reason: duplication that exists now, a structure the user asked for, or a need the next known slice requires. Tests stay untouched and green.
4. **Show.** Summarize the change in one or two lines and point to the diff.
5. **Commit.** Propose a Conventional Commit for the test and code as one work unit. Commit only when the user has authorized commits for this feature.

In "pair" mode, stop after step 4 of every test and wait. Otherwise continue through the test list and stop when the slice is done.

## Alarms: stop and report

- **Loop:** the same failure twice after a fix attempt.
- **Scope creep:** code, fields, endpoints, abstractions, or files that `## Now` does not need. Remove them or ask.
- **Test cheating:** editing, skipping, deleting, or weakening a test, or special-casing test input, to get green.

## Close the slice

1. Check every acceptance criterion against observed evidence: test output, or a command or URL the user can use to try it.
2. Ask the user to try the slice. On their go-ahead, load the `story` skill yourself for the next unchecked slice.
3. In the working file, check the slice in `## Backlog`, clear `## Now`, and add a Log line with evidence and commits. Update the Engram mirror.
4. Report the outcome, any failed, skipped, or pending check, and `Risk: none` or `Risk: <item> (reason)`.
5. After the last slice, delete `.slices/<feature>.md` and save a final Engram note marking the feature closed.
