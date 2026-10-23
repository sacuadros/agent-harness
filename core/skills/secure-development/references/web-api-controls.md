# Web and API controls

Apply only the sections relevant to the changed trust boundary.

## Authorization and tenancy

- Deny by default and authorize every request server-side.
- Check the requested object, action, role, tenant, and current resource state.
- Test unauthenticated, horizontal, vertical, and cross-tenant access.
- Derive identity and tenant from trusted session context, not mutable client fields.
- Keep administrative paths behind explicit policy, audit, and step-up authentication when impact warrants it.

## Authentication and sessions

- Reuse proven framework/session primitives; do not design a custom protocol.
- Prevent account enumeration with consistent messages and materially similar timing.
- Rotate or invalidate sessions after login, privilege change, recovery, credential change, and suspected compromise.
- Require reauthentication or step-up for high-impact actions.
- Protect cookies and tokens with appropriate transport, scope, expiry, revocation, and replay controls.

## Input, output, and injection

- Validate syntax and business meaning at the trust boundary; prefer allowlists.
- Use parameterized database and command APIs. Do not build queries or shell commands through concatenation.
- Encode output for its destination context. Validation alone does not prevent XSS, SQL injection, or command injection.
- Reject unknown mass-assignment fields and enforce property-level authorization.
- Bound size, count, nesting, complexity, timeout, concurrency, and cost.

## URLs, files, and external systems

- For user-controlled URLs, allowlist schemes and destinations, resolve DNS safely, block private/link-local/metadata ranges, limit redirects, and enforce egress policy.
- For uploads, validate size, declared and detected type, extension, filename, archive expansion, storage location, and access policy; serve as inert content where possible.
- Treat webhook signatures, timestamps, replay windows, idempotency, and duplicate delivery as one control set.
- Validate external API responses before using them in trusted decisions; fail closed for authorization and integrity decisions.

## Secrets, cryptography, and sensitive data

- Store secrets centrally, scope access, prefer short-lived credentials, rotate, revoke, and audit use.
- Never place secrets or sensitive payloads in source, URLs, client bundles, logs, traces, analytics, errors, or model context.
- Use platform cryptography with documented algorithms and key lifecycle; never invent primitives or silently downgrade.
- Minimize collection, retention, replication, and response fields for sensitive data.

## State changes, payments, and exceptional conditions

- Protect browser state changes against CSRF when ambient credentials are used; configure CORS narrowly and independently from authorization.
- Make retryable high-impact operations idempotent and detect replay or duplicate execution.
- Validate business sequence and resource state, not only field formats.
- Fail safely on timeout, dependency error, partial completion, and malformed response; do not grant access or report success ambiguously.
- Log security-relevant authentication, authorization, validation, administrative, secret, and integrity events without logging sensitive values.
