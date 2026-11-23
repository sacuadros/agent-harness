---
name: verification-ladders
description: "Choose the checks a change needs from the surfaces it touches (backend, frontend, database, infra) and its assurance level. Use before reporting that a Standard or Critical change works, or when the user asks how to verify a change."
---

# Verification Ladders

What you report is not evidence. A rung counts only when its command ran after the final diff and you read its output.

## 1. Name the surfaces

Read the diff and list every surface it touches:

- **Backend:** server code, API handlers, services, jobs.
- **Frontend:** components, styles, client state, routes.
- **Database:** schema, migrations, queries, seeds.
- **Infra:** Dockerfiles, CI workflows, infrastructure code, deploy config.

## 2. Climb each ladder to your assurance level

Each level includes the rungs of the levels before it. Use the repository's own commands. If the repository has no tooling for a rung, skip it and say so; ask before adding a tool to satisfy one.

| Surface | Basic | Standard adds | Critical adds |
|---|---|---|---|
| Backend | typecheck or lint, and the focused unit test | an integration or contract test of the changed behavior; when a public API changed, its diff (OpenAPI or exported types) and its consumers | an end-to-end call against the running service, and the checks for the named risk (authorization, input validation, data loss) |
| Frontend | typecheck, and the focused component test | the changed flow in a real browser, with its error and empty states | accessibility of the changed screen, narrow and wide widths, and visual regression when the repository keeps snapshots |
| Database | queries run against a real database, not a mock | (migrations start at Critical) | migrate an empty database to latest; migrate the previous version with realistic data to latest; roll back when the tool supports it; rerun the queries that touch the changed tables |
| Infra | the config parses (lint or dry run) | build or run it in a disposable environment: a local image build, a branch workflow run, a plan | the same against a copy of the real target; never verify in production |

Any migration and any infra change that reaches production is at least Critical, because the instructions name both as risk items.

## 3. Cross the surfaces once

When the diff touches two or more surfaces, finish with one pass through the real flow: start from a clean state, run the flow as a user would, confirm the data persisted, restart the services, and confirm it again.

## 4. Mutation testing, only when it pays

Run it for Critical changes, on the changed modules only, and only when the repository already has a mutation tool. A surviving mutant in changed code means a test is missing; add that test.

## 5. Report

For each surface: the rung reached, the command, and its result. List every skipped rung with the reason. A failed rung means the change is not done.

## Rules

- Generate and compare screenshots in the same environment as the baselines; rendering changes with the operating system, fonts, and hardware.
- Stop repairing after the same failure twice: diagnose the root cause (`systematic-debugging`) instead of trying again.
- When the risk item is security, load the `secure-development` skill for the controls to verify.
- Never weaken, skip, or delete a check to reach a rung.
