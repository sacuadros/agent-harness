---
name: dependency-safety
description: Evaluate external package or CLI additions and upgrades for official versions, compatibility, provenance, lifecycle behavior, vulnerabilities, and supply-chain risk.
---

# Dependency Safety

Apply one evidence gate before implementation. Reduce risk; never claim that a package is guaranteed safe.

## 1. Avoid the dependency when possible

1. Check whether the repository already provides the capability.
2. Prefer standard-library, platform-native, or already-installed solutions.
3. Do not introduce an incidental dependency without explaining why existing options fail. Ask before adding it when the user did not request it.

## 2. Establish the live project baseline

1. Read the repository's manifest, lockfile, runtime version, and package-manager configuration.
2. Determine the exact currently resolved version, not only the declared range.
3. Reuse the repository's package manager and existing security controls. Never switch package managers as part of this gate.
4. Separate facts verified from files or tools from assumptions and recommendations.

## 3. Validate documentation and stable version

1. Resolve the official Context7 library ID, then query the narrow documentation needed for the task. Prefer version-specific documentation when available.
2. Confirm the latest stable release through the official registry, upstream release page, or official vendor documentation. Context7 alone does not prove the latest stable version.
3. Exclude prerelease, beta, RC, canary, nightly, deprecated, or yanked versions unless the user explicitly requests one.
4. Check runtime requirements, peer dependencies, migration notes, breaking changes, and compatibility with the existing lockfile.
5. Prefer the newest compatible stable version, not blindly the numerically newest release.
6. If Context7 is unavailable or lacks the library, use primary official documentation and disclose the fallback. Never guess an API or version.

## 4. Review supply-chain risk

Before installing or approving a dependency, inspect the evidence that applies:

- exact package name, registry namespace, upstream repository, and publisher identity;
- registry credentials only as redacted configuration evidence; never print or copy secret values, and treat plaintext tokens as separate urgent rotation/removal work;
- suspicious spelling, dependency-confusion exposure, ownership changes, release age, and unexpected maintenance changes;
- known vulnerabilities using the ecosystem-native audit and OSV when available;
- provenance, registry signatures, signed releases, or SLSA attestations when the ecosystem publishes them;
- lifecycle scripts, native binaries, generated executables, network downloads, and privileged behavior;
- direct and transitive dependency growth, licenses, and abandoned or archived upstream status;
- OpenSSF Scorecard details as a heuristic only, never as a pass/fail guarantee.

Block a selected version with an applicable known critical or high vulnerability until there is a fixed version or an explicit, justified, time-bounded exception. Do not run automatic fix commands that rewrite dependency trees without reviewing the proposed changes.

If the ecosystem-native audit endpoint is unavailable, retired, or returns an invalid response, treat the vulnerability check as failed, not clean. Fall back to repository-host alerts or OSV, record the gap, and avoid automatic tree rewrites.

## 5. Implement safely

1. Pin through the repository's normal manifest policy and commit the lockfile.
2. Use frozen or immutable lockfile installs in CI.
3. Review manifest and lockfile diffs, including new transitive dependencies.
4. Prevent unreviewed lifecycle scripts from running when the package manager supports allowlisting.
5. Run the smallest relevant audit, tests, type checks, lint, and build.
6. Re-run the vulnerability check against the resolved post-change lockfile.
7. In GitHub Actions, pin third-party actions to a full commit SHA, grant the minimum `permissions`, and never expose secrets to untrusted pull-request code.
8. For `pull_request_target` or `workflow_run`, inspect the checked-out ref and effective checkout release; a full SHA pin prevents drift but does not receive upstream hardening automatically.
9. Enable repository-native dependency alerts, malware alerts, dependency review, and secret push protection when the hosting plan supports them. Keep updates review-gated; do not auto-merge them.

## Stable supply-chain baseline

Use the current stable [OpenSSF OSPS Baseline](https://baseline.openssf.org/), [SLSA specification](https://slsa.dev/spec/), and [NIST SSDF](https://csrc.nist.gov/projects/ssdf/publications) to identify applicable gaps. As of 2026-07-16, the stable references are OSPS Baseline v2026.02.19, SLSA 1.2, and SSDF 1.1; reverify before citing them because newer drafts or releases must not silently become policy. Keep application security in `secure-development`; this skill owns dependencies and supply chain.

## Ecosystem controls

Apply only controls supported by the repository's installed package-manager version and verify their current syntax through Context7 or official docs.

### pnpm

Read `references/pnpm.md` only when the repository actually uses pnpm. Verify every option against the effective pnpm major before recommending it.

### npm

- Use `npm audit` for known vulnerabilities.
- Use `npm audit signatures` when the project uses npm's lockfile and a compatible npm CLI.
- Never create a `package-lock.json` or run npm installation commands in a pnpm, Yarn, or Bun project just to use npm audit.

### Other ecosystems

Use the repository's native audit and integrity mechanisms first. Add OSV-Scanner only when it materially improves multi-ecosystem or CI coverage; do not add tooling speculatively.

## Required result

Report this evidence compactly before or with the implementation:

```text
Dependency evidence
- Package and purpose:
- Current resolved version:
- Latest stable version:
- Selected version:
- Context7 documentation:
- Official release source:
- Compatibility constraints:
- Known vulnerabilities:
- Provenance or signatures:
- Lifecycle scripts or binaries:
- Transitive impact:
- Decision: ACCEPT / REJECT / EXCEPTION
- Residual risk:
```

For an exception, include owner, reason, compensating control, and expiry date.

## Boundaries

- Do not promise that a dependency is malware-free.
- Do not use download counts, stars, popularity, or a single scanner as proof of safety.
- Do not update unrelated dependencies.
- Do not auto-merge dependency updates.
- Do not replace repository-specific CI or security policy; follow the stricter applicable rule.
