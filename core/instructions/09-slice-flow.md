## Slice Flow

Build in small vertical slices; you drive and the user steps in only when needed. Plan only what the next slice needs; never write a full upfront spec.

1. **Authorize.** Investigation, explanation, review, audit, comparison, and proposal requests stay read-only: no writes, no writer subagents, no artifacts. If change intent is ambiguous, ask one question and stay read-only.
2. **Size by the resume test.** Work is small when one bounded look explains it, it touches no risk item (step 7), and someone could finish it from the request plus `git diff` alone. Small work stays inline with no backlog or story. Never size by file, test, or task count.
3. **Large work gets a backlog.** When the resume test fails (several sessions, separate deliverables, external waits, requirements too long to survive compaction), load the `backlog` skill yourself before the first write: one-line vertical slices, each usable end to end, ordered by value, cheap to drop. The working file is `.slices/<feature>.md`, excluded through `.git/info/exclude`, with `## Specs` (the user's requirements verbatim as S1..Sn, assumptions marked), `## Backlog`, `## Now`, and `## Log` (L1 is the original request verbatim, then dated corrections and decisions). Mirror it to Engram (`topic_key: slices/<feature>`, `capture_prompt: false`) after each slice; on resume read Engram, then the file, and reconcile. Delete the file when the feature closes; commits keep the history.
4. **Refine just in time.** Load the `story` skill for the next slice only: Given/When/Then acceptance criteria, an ordered test list, out of scope, and open questions. Do not detail later slices.
5. **Build with the `pair` skill.** One test at a time: RED, minimal GREEN, then refactor only for a stated reason. Stage each accepted test (`git add`) before writing the code that makes it pass, so any later test edit shows in `git diff`; test and code form one work unit for the commit proposal. Never weaken, skip, or delete a test to get green without saying so. Add no abstraction, layer, or field the current slice does not need.
6. **Pace.** Run on your own; the user steps in only when needed. Chain the skills yourself and never ask the user to type a command. Large work has one checkpoint before building: backlog approval. After it, write each story and build every slice in order without waiting, recording assumed answers in the Log. Stop only for:
   - a product decision only the user can make;
   - an action that needs the user's approval: commit, push, PR, merge, publish, deploy, remote operations, or anything destructive;
   - a `pair` alarm;
   - the end of the backlog.

   Run required checks, independent reviews, and CI watches without asking; bring back only findings that need a decision. The user can slow down at any time: "pair" stops after every RED→GREEN step, "con pausas" stops after each slice, and "para" stops now.
   - **Asking.** When you must ask, ask everything pending in one round. Offer 2-3 options with your recommendation first, through {{agent}}'s question tool when it has one. Otherwise use a numbered list the user answers with a number.
   - **Commits.** Commits and pushes always wait for the user. At the end, or when the user stops, propose the commits and ask once with options such as commit, commit and push, or not yet. Make one Conventional Commit per slice when their files do not overlap; otherwise make one for the feature.
7. **Risk line.** Close every code change with `Risk: none` or `Risk: <item> (reason)`. Items: irreversible data or migrations, security, contracts others consume (shared code counts), concurrency, delivery or environment, and no test that would catch a regression. A named item raises assurance to Critical.
8. **Close.** Report the verified outcome, every failed, skipped, or pending check, and the commit proposal. Commit, push, PR, merge, publish, and deploy remain separately authorized.

Assurance (Basic, Standard, Critical) sets verification depth independently of slice size. Apply process skills (for example `systematic-debugging`) selectively inside this flow; Slice Flow is the only planning authority, so they must not create parallel plans or spec artifacts. If a skill or hook requires a pause or work outside the flow, name its source and complete unaffected authorized work.

Repositories that already contain `openspec/` keep it as project history; continue an OpenSpec change there only when the user asks.

Use CodeGraph, Engram, Context7, Git, and {{agent}} capabilities directly. Do not invoke wrapper installers or ecosystem configurators.
