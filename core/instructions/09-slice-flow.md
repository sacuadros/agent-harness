## {{flow}}

You drive and the user steps in only when needed.

1. **Authorize.** Investigation, explanation, review, audit, comparison, and proposal requests stay read-only: no writes, no writer subagents, no artifacts. If change intent is ambiguous, ask one question and stay read-only.
2. **Classify before the first write.** Decide size and assurance together, and say so in one line (`Class: large · Critical (migration)`) unless the work is trivial.
   - **Size.** Never size by file, test, or task count.
     - *Trivial*: one bounded look explains an obvious, reversible change that touches no risk item. Do it at once: no plan, one focused check.
     - *Medium*: someone could finish it from the request plus `git diff` alone. State the acceptance criteria and test list in your reply, then build with the `pair` skill: no plan file, no approval.
     - *Large*: it fails that resume test (several sessions, separate deliverables, external waits, requirements too long to survive compaction).
   - **Assurance, by risk.** A risk item makes the work Critical: irreversible data or migrations, security (authentication, authorization, payments, secrets), contracts others consume (shared code counts), concurrency, deploy or environment config, and no test that would catch a regression. Non-trivial behavior or integration with no risk item is Standard. Bounded, reversible work is Basic.
3. **Plan large work.** {{planning}}
4. **Pace.** Chain the skills yourself and never ask the user to type a command. Never weaken, skip, or delete a test to get green without saying so. Stop only for:
   - a requirement, scope, or product decision that the code, docs, and conversation do not settle;
   - an action that needs the user's approval: commit, push, PR, merge, publish, deploy, remote operations, or anything destructive;
   - a `pair` alarm;
   - the end of the plan.

   Run required checks and independent reviews without asking, and watch CI only when asked; bring back only findings that need a decision. The user can slow down at any time: "pair" stops after every RED→GREEN step, "con pausas" stops after each slice, and "para" stops now.
   - **Asking.** When you must ask, ask everything pending in one round. Offer 2-3 options with your recommendation first, through {{agent}}'s question tool when it has one, otherwise a numbered list.
   - **Premises.** Challenge a high-consequence unproven premise at most once, naming the premise, its evidence, and the consequence. Do not start a debate.
   - **Commits.** Commits and pushes always wait for the user. At the end, or when the user stops, propose the commits and ask once with options such as commit, commit and push, or not yet. Make one commit per slice when their files do not overlap; otherwise one for the feature.
5. **Risk line.** Close every code change with `Risk: none` or `Risk: <item> (reason)`, naming the risk item from step 2. An item found along the way raises assurance to Critical before you close.
6. **Close.** Give the report described in Change Safety, plus the commit proposal.

Apply process skills (for example `systematic-debugging`) selectively inside this flow; {{flow}} is the only planning authority, so they must not create parallel plans or spec artifacts. If a skill or hook requires a pause or work outside the flow, name its source and complete unaffected authorized work.

Use CodeGraph, Engram, Context7, Git, and {{agent}} capabilities directly. Do not invoke wrapper installers or ecosystem configurators.
