# pnpm controls

Read `packageManager`, the lockfile, workspace configuration, registry configuration, and the effective pnpm version first. Run the repository-pinned major; never copy settings from newer documentation into an older project.

## pnpm 11

- Set `minimumReleaseAge: 1440` explicitly when a one-day publication cooldown fits the repository's release policy.
- Use `minimumReleaseAgeIgnoreMissingTime: false` only when every registry or mirror publishes reliable timestamps; otherwise document the fail-open compatibility tradeoff.
- Prefer `trustPolicy: no-downgrade` when supported.
- Keep `trustLockfile: false`, `verifyStoreIntegrity: true`, `strictStorePkgContentCheck: true`, and `strictSsl: true` when supported by the effective version.
- Use `strictDepBuilds: true` with an explicit `allowBuilds` map after reviewing each lifecycle script. Never enable `dangerouslyAllowAllBuilds`.
- Do not recommend `onlyBuiltDependencies`; it was removed in pnpm 11.
- Keep `blockExoticSubdeps: true` when supported.
- Prefer `pmOnFail: error` to enforce the declared package manager.

## pnpm 10

- On pnpm 10.26+, prefer `strictDepBuilds: true` plus an explicit `allowBuilds` map after reviewing each lifecycle script.
- On pnpm 10.25 or earlier, use that version's documented build-script allowlist controls.
- Verify cooldown, trust, integrity, and exotic-dependency options against documentation for the exact installed minor before changing configuration.

## pnpm 9

- Use `onlyBuiltDependencies` only after reviewing each lifecycle script.
- Do not recommend `minimumReleaseAge`, `allowBuilds`, `strictDepBuilds`, `blockExoticSubdeps`, `trustPolicy`, or `pmOnFail`; they are not available in pnpm 9.
- Keep `strictSsl`, `verifyStoreIntegrity`, and `strictStorePkgContentCheck` enabled, and inspect publication age and exotic dependency specifications manually.
- If an applicable security fix exists only in a maintained major, report a separate package-manager upgrade decision; never migrate majors inside this gate.

## Shared boundaries

- Do not share a pnpm store across mutually untrusted users or CI jobs.
- Use a narrow package-and-version cooldown exclusion for an urgent security fix; never disable the policy globally.
- Treat a pnpm major migration as a separate reviewed change.
- If the native audit endpoint is unavailable, retired, or invalid, treat the check as failed and use repository-host alerts or OSV without rewriting the dependency tree automatically.
